# lib/ocr_engine.py
from __future__ import annotations
import os
import json
import re
import math
import statistics
import logging
import time
from groq import Groq
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Initialize globally
try:
    import easyocr

    reader = easyocr.Reader(["en"], gpu=False)
except ImportError:
    reader = None

groq_key = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=groq_key) if groq_key else None

STORE_PATTERNS = {
    "Co-op": ["co-op", "owned by you", "coop", "perne road"],
    "Sainsbury's": ["sainsbury", "nectar", "coldhams lane"],
    "Tesco": ["tesco", "clubcard", "petty cury"],
    "Aldi": ["aldi"],
    "Lidl": ["lidl", "nicolson street"],
    "Morrisons": ["morrisons", "morrison", "southwark"],
    "Waitrose": ["waitrose"],
}

STOPWORDS = [
    "change",
    "credit",
    "debit",
    "auth code",
    "merchant",
    "cryptogram",
    "expiry",
    "tid:",
    "aid:",
    "card no",
    "member card",
    "thank you",
    "reward balance",
    "please keep",
    "transaction",
    "points earned",
    "nectar summary",
    "vat number",
    "balance due",
    "total",
    "subtotal",
    "vat rate",
    "sales £",
    "checkout:",
    "checkout",
    "till",
    "store:",
    "txn",
    "trns",
    "op ",
    "gift card",
    "cash",
    "balance",
]

VALID_SUPERMARKETS = [
    "tesco",
    "sainsbury",
    "morrison",
    "aldi",
    "lidl",
    "co-op",
    "coop",
    "waitrose",
    "asda",
    "iceland",
    "m&s",
    "marks & spencer",
]

# HEALED REGEX: Allows common OCR misreads for decimal dividers (e.g., E1.R9, E},69, 1:49)
PRICE_PATTERN = re.compile(r"([£€E]?\s*\d+[.,:;R\}]\s*\d{2})", re.IGNORECASE)

_ITEM_NAME_ALIASES = (
    "name",
    "description",
    "item_name",
    "product",
    "product_name",
    "item",
    "label",
    "text",
    "item_description",
    "item_text",
)


def preprocess_image(file_bytes: bytes) -> bytes:
    """Applies adaptive thresholding to flatten shadows and enhance text."""
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 15
    )
    _, buf = cv2.imencode(".jpg", thresh)
    return buf.tobytes()


def detect_store(text_blob: str):
    text_blob = text_blob.lower()
    for store, keywords in STORE_PATTERNS.items():
        if any(keyword in text_blob for keyword in keywords):
            return store
    return "Unknown"


def deskew_positions(results):
    """Computes dominant text baseline tilt and straightens coordinates."""
    angles = []
    for bbox, _, _ in results:
        dx = bbox[1][0] - bbox[0][0]
        dy = bbox[1][1] - bbox[0][1]
        if dx != 0:
            angles.append(math.atan2(dy, dx))

    median_angle = statistics.median(angles) if angles else 0.0

    if abs(median_angle) < 0.005:
        return results

    cos_a, sin_a = math.cos(-median_angle), math.sin(-median_angle)
    deskewed_results = []

    for bbox, text, conf in results:
        new_bbox = []
        for x, y in bbox:
            nx = x * cos_a - y * sin_a
            ny = x * sin_a + y * cos_a
            new_bbox.append([nx, ny])
        deskewed_results.append((new_bbox, text, conf))

    return deskewed_results


def group_into_lines(results):
    """Groups text using an adaptive Center-to-Center anchor to prevent vertical line collisions."""
    lines_data = []

    for bbox, text, _ in results:
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        word_height = bbox[2][1] - bbox[0][1]

        placed = False
        for line in lines_data:
            line_y_centers = [(item[0][0][1] + item[0][2][1]) / 2 for item in line]
            avg_line_y_center = sum(line_y_centers) / len(line_y_centers)
            line_heights = [item[0][2][1] - item[0][0][1] for item in line]
            avg_line_height = sum(line_heights) / max(len(line_heights), 1)

            if abs(y_center - avg_line_y_center) <= (
                max(word_height, avg_line_height) * 0.80
            ):
                line.append((bbox, text))
                placed = True
                break

        if not placed:
            lines_data.append([(bbox, text)])

    lines_data.sort(
        key=lambda line: sum((item[0][0][1] + item[0][2][1]) / 2 for item in line)
        / len(line)
    )

    final_lines = []
    for line in lines_data:
        line.sort(key=lambda x: x[0][0][0])
        final_lines.append(" ".join(text for _, text in line))

    return final_lines


def _pair_orphaned_prices(lines: list) -> list:
    """Secondary fallback recovery loop matching floating names to prices."""
    items = []
    i = 0
    while i < len(lines):
        current = lines[i]

        if any(word in current.lower() for word in STOPWORDS):
            i += 1
            continue

        if PRICE_PATTERN.search(current):
            i += 1
            continue

        if i + 1 < len(lines):
            next_line = lines[i + 1]
            price_match = PRICE_PATTERN.search(next_line)
            if price_match:
                remainder = PRICE_PATTERN.sub("", next_line).strip()
                if len(remainder) <= 3:
                    desc = current.strip()
                    if len(desc) > 2 and not desc.isdigit():
                        try:
                            price_str = (
                                re.sub(r"[£€Ee\s]", "", price_match.group(1))
                                .replace(",", ".")
                                .replace("R", ".")
                                .replace("}", ".")
                            )
                            price = float(price_str)
                            items.append(
                                {"raw_string": desc, "unit_price": price, "quantity": 1}
                            )
                            i += 2
                            continue
                        except ValueError:
                            pass
        i += 1

    logger.info(f"Orphaned price pairing recovered {len(items)} items")
    return items


def extract_receipt_data_via_llm(text_blob: str) -> dict | None:
    """Leverages the structural contextual processing capacity of Llama 3 to parse receipts."""
    if not groq_client:
        logger.warning("Groq client not initialized. Skipping LLM extraction.")
        return None

    system_instruction = (
        "You are an advanced retail receipt intelligence document parser built specifically for UK supermarkets.\n"
        "Analyze the provided raw text lines extracted from a grocery receipt and convert them into a clean structured JSON format.\n\n"
        "Rules:\n"
        "1. CRITICAL - STRICT STORE IDENTIFICATION: Identify the store_name EXACTLY as printed at the top of the receipt (e.g., 'Starbucks', 'B&Q', 'Tesco'). Do NOT guess or force a supermarket name if the receipt belongs to a restaurant, hardware store, or clothing retailer.\n"
        "2. CRITICAL - SCREENSHOT METADATA BAN: Completely ignore mobile phone status bar indicators.\n"
        "3. CRITICAL - LOYALTY DISCOUNTS & MEAL DEALS: Discounts apply to the parent item ABOVE them... \n"
        "   - TESCO CLUBCARD TRAP: Tesco prints the target discounted price inline... \n"
        "   - POSITIVE DISCOUNT TRAP: Stores like Co-op print discounts as positive numbers...\n"
        "   - MULTI-SAVE & DOUBLE NEGATIVES: If you see a standalone 'Multi-save' row...\n"
        "   - CO-OP POST-BALANCE DISCOUNTS: Co-op prints discounts (e.g., 'Co-op Bakery Offer') AFTER the 'BALANCE DUE' line. Do NOT stop reading items when you hit the balance. You MUST scan below the balance line, extract these discounts, and apply them to the relevant item above.\n"
        "4. CRITICAL - MULTI-LINE PRODUCTS & SANDWICHED DESCRIPTIONS: Collapse consecutive rows of a single product into ONE entry. If an item description wraps to a second line (e.g., 'Walkers Crisps' on line 1, 'Sweet Chilli 150g' on line 2), DO NOT split them into two items. If a descriptive string (like '- Original 380ml') is sandwiched between a parent item and its discount, you MUST merge the description into the parent's 'raw_string' and apply the discount directly to the parent. Ensure you lock the base_price to the EXACT positive number printed on the extreme right of the parent item's row.\n"
        "5. CRITICAL - DATE EXTRACTION: Extract the exact printed transaction date. You MUST explicitly IGNORE credit card 'EXPIRY' or 'EXP' dates (e.g., '09/28'). Convert the extracted date strictly to YYYY-MM-DD format (e.g., '11/06/26' MUST become '2026-06-11'). Do not output slashes.\n"
        "6. CRITICAL - QUANTITY MULTIPLIERS & LEADING INTEGERS: Look for inline multipliers (e.g., '5 x £1.75') OR leading standalone integers at the very start of a line (e.g., '2 M SPINACH' means quantity 2). You MUST extract the exact quantity AND completely remove that leading integer and any multiplier symbols from the final 'raw_string' output (e.g., output 'M SPINACH', not '2 M SPINACH'). "
        "EXCEPTION: NEVER apply this rule to payment or summary lines. Lines containing words like 'BALANCE DUE', 'GIFT CARD', 'TOTAL', 'CASH', or 'CHANGE' are NOT items — a leading integer there is part of the payment structure, not a product quantity. Skip them entirely.\n"
        "7. CRITICAL - EXTENDED TAX LETTERS & OCR MUTATIONS: UK supermarkets append tax letters (A, B, C, D, E, F, V, or *) to the far right. Ignore them. WARNING: OCR frequently misreads 'F' as '5' or '8', 'B' as '8', and 'A' as '4'. DISCARD THESE.\n"
        "8. CRITICAL - OCR NOISE & THE '8' / '5' MUTATION: OCR heavily misreads the '£' symbol as the number '8' or '5', leading to massively inflated prices (e.g., OCR reads '£5.50' as '85.50' or '55.50'). Single grocery items rarely cost over £20. If you see a suspiciously high price starting with an 8 or a 5 (e.g., 54.10, 89.20), you MUST assume the leading digit is a mangled '£' sign. Drop the leading '8' or '5' and extract the remaining float (e.g., '85.50' becomes 5.50, '54.10' becomes 4.10). Strip all other currency characters.\n"
        "9. CRITICAL - DUAL PRICE COLUMNS & LINE TOTALS: If you see BOTH a Unit Price and a Line Total on the same row (e.g., '5 x £1.75 8.75'), you MUST extract the smaller unit price (£1.75) as the 'base_price', and the explicit final larger amount (£8.75) as the 'line_total'. Do NOT ignore the line total.\n"
        "10. CRITICAL - TOTAL EXTRACTION vs PAYMENT METHODS: Extract the final net total cost of the basket. This is usually labeled 'BALANCE DUE', 'TOTAL', or 'AMOUNT DUE'. You MUST explicitly ignore 'Subtotal', 'Savings', or 'Promotions' lines when determining the final total. Explicitly ignore any lines detailing how the customer paid (e.g., 'GIFT CARD', 'CASH') UNLESS you are dealing with a Co-op receipt. NEVER extract 'GIFT CARD' as a physical grocery product in the `items` array.\n"
        "11. CRITICAL - HEADER GLUE, ORPHANED PRICES & MISALIGNMENT: OCR engines frequently suffer from vertical misalignment on wavy receipts. If you see a row containing column headers glued directly to prices (e.g., 'QTY DESCRIPTION PRICE £1.89 Total £1.89' or 'aty ITeim Pr ica E1.R9 Totul E},69'), and the actual item description (e.g., '1 Red Seedles Grap') is isolated on the row immediately below or around it, you MUST merge them together into a single item. NEVER drop an item just because its price was grouped with the header or split onto an adjacent baseline.\n"
        "12. CRITICAL - VOIDS, CANCELLATIONS, & REFUNDS: A voided item will appear with a 'VOID' or 'LESS' prefix, ALONGSIDE A NEGATIVE CURRENCY VALUE on the exact same line. Do NOT confuse a hyphenated product description (e.g., '- Original 380ml') with a void. If a line just has text and no negative price, it is a product continuation, not a void. NEVER output a standalone item with a negative base_price or a negative quantity.\n"
        "13. CRITICAL - THE VOLUME/WEIGHT TRAP: Supermarket items often contain volume or weight metrics in the name (e.g., '1.75L', '500g', '1KG', '2.5L'). NEVER extract these numbers as the base_price. Ignore any float attached to a metric unit and look further right for the actual currency price.\n"
        "14. CRITICAL - IDENTICAL REPEATING ROWS: If a customer buys multiples of the same item and the store prints them on individual, consecutive lines, each with its own price (e.g., four consecutive lines of '*NESTLE WTR 12X500ML £2.65'), you MUST count how many times the row appears. Combine them into a single item, extract the single unit price (£2.65) as the 'base_price', and set the 'quantity' to the exact number of times the row appeared (e.g., 4). NEVER merge them and leave the quantity at 1.\n"
        "15. CRITICAL - SAINSBURY'S NECTAR SUMMARY: Sainsbury's receipts include a 'MY NECTAR SUMMARY' block that begins after a line of asterisks (***...). This section contains loyalty point balances and values (e.g., 'POINTS EARNED ON £2.74', 'POINTS EARNED 2'). You MUST completely ignore this entire block. NEVER extract items, discounts, prices, or totals from within it — including any £ values that coincidentally match item prices.\n"
        "16. CRITICAL - SAINSBURY'S OWN-BRAND PREFIXES: Sainsbury's prefixes product names with store codes. 'JS' = Sainsbury's own brand. Codes like 'SSTC', 'SO', 'TT', 'HBR' are internal category markers. Strip ALL such prefixes from the 'raw_string'. E.g., 'JS SSTC GRAPE 500G' → raw_string: 'GRAPE 500G'. Combined with Rule 14: if 'JS SSTC GRAPE 500G £1.37' appears on TWO consecutive lines, output ONE item: {raw_string: 'GRAPE 500G', base_price: 1.37, quantity: 2, line_total: 2.74}.\n\n"
        "Expected Output Schema — you MUST use exactly these key names:\n"
        "{\n"
        '  "store_name": "Sainsbury\'s",\n'
        '  "date": "2026-06-11",\n'
        '  "total": 2.74,\n'
        '  "items": [\n'
        '    {"raw_string": "GRAPE 500G", "base_price": 1.37, "line_total": 2.74, "discount_applied": 0, "discount_type": null, "quantity": 2}\n'
        "  ]\n"
        "}"
    )

    try:
        logger.info(
            f"🧠 Sending {len(text_blob)} chars to Groq Llama 3.3 for structural parsing..."
        )
        start_llm = time.time()

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Raw Receipt Text Lines:\n{text_blob}"},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        llm_elapsed = time.time() - start_llm
        raw_response = completion.choices[0].message.content

        logger.info(f"⏱️ Groq LLM responded in {llm_elapsed:.2f}s")
        logger.info(f"📄 LLM Raw JSON Output:\n{raw_response}")

        parsed_data = json.loads(raw_response)

        if "items" not in parsed_data or not isinstance(parsed_data["items"], list):
            logger.error(
                "🚨 LLM Schema Violation: 'items' array missing or malformed in JSON response."
            )

        return parsed_data
    except json.JSONDecodeError as e:
        logger.error(f"🚨 LLM returned invalid, non-parseable JSON structure: {e}")
        return None
    except Exception as e:
        logger.error(f"Groq intelligent document parser error: {e}", exc_info=True)
        return None


def extract_receipt_data_fallback(lines, full_text_dump: str):
    """Regex-based fallback parser invoked when the LLM returns no usable items."""
    store_name = detect_store(full_text_dump)
    items = []
    for line in lines:
        if any(word in line.lower() for word in STOPWORDS):
            continue
        match = PRICE_PATTERN.search(line)
        if match:
            clean_price_str = (
                re.sub(r"[£€Ee\s]", "", match.group(1))
                .replace(",", ".")
                .replace("R", ".")
                .replace("}", ".")
                .replace(":", ".")
            )
            try:
                price = float(clean_price_str)
                desc = line[: match.start()].strip()
                if len(desc) > 2 and not desc.isdigit():
                    items.append(
                        {"raw_string": desc, "unit_price": price, "quantity": 1}
                    )
            except ValueError:
                continue

    logger.info(
        f"Regex fallback extracted {len(items)} items: {[i['raw_string'] for i in items]}"
    )

    if not items:
        logger.warning(
            "⚠️ Primary regex pass found 0 items. Trying orphaned price pairing..."
        )
        items = _pair_orphaned_prices(lines)

    return {
        "store_name": store_name,
        "items": items,
        "total": round(sum(i["unit_price"] for i in items), 2),
        "date": None,
    }


def extract_receipt_data(file_bytes: bytes):
    """Core processing script. Parses raw image streams into structured payloads."""
    if reader is None:
        logger.warning(
            "Executing in Lean Production Web Layer. Direct OCR execution disabled."
        )
        return {}

    logger.info("Executing heavy EasyOCR sequence...")
    try:
        logger.info("----- OCR START -----")
        clean_bytes = preprocess_image(file_bytes)
        results = reader.readtext(clean_bytes, detail=1)

        logger.info(f"EasyOCR detected {len(results)} text regions from image")

        straightened_results = deskew_positions(results)
        lines = group_into_lines(straightened_results)
        full_text_dump = "\n".join(lines)

        logger.info(f"Raw Extracted Text Length: {len(full_text_dump)} chars")
        logger.info(f"Raw Extracted Text Dump:\n{full_text_dump}")

        structured_data = extract_receipt_data_via_llm(full_text_dump)

        if structured_data and "store_name" in structured_data:
            detected_store = structured_data.get("store_name", "").lower()
            is_valid = any(valid in detected_store for valid in VALID_SUPERMARKETS)

            if not is_valid:
                logger.error(
                    f"🛑 REJECTED: '{structured_data.get('store_name')}' is not a supported UK Supermarket."
                )
                return {
                    "store_name": "REJECTED",
                    "items": [],
                    "total": 0.0,
                    "date": None,
                }

        if structured_data and "items" in structured_data:
            for item in structured_data.get("items", []):
                if "raw_string" not in item:
                    for alias in _ITEM_NAME_ALIASES:
                        if item.get(alias):
                            item["raw_string"] = str(item[alias])
                            logger.info(
                                f"Key heal: mapped '{alias}' → 'raw_string' for: {item[alias]!r}"
                            )
                            break
                    else:
                        item["raw_string"] = ""

            structured_data["items"] = [
                item
                for item in structured_data["items"]
                if item.get("raw_string") and str(item["raw_string"]).strip() != ""
            ]

            if not structured_data["items"]:
                logger.warning(
                    "⚠️ AI returned no valid items. Triggering regex structure fallback..."
                )
                return extract_receipt_data_fallback(lines, full_text_dump)

            for item in structured_data["items"]:
                if item.get("base_price") is None:
                    if item.get("line_total") is not None and item.get("quantity"):
                        item["base_price"] = float(item["line_total"]) / int(
                            item["quantity"]
                        )
                    else:
                        item["base_price"] = 0.0

                if item.get("discount_applied") is None:
                    item["discount_applied"] = 0.0

                if item.get("line_total") is None:
                    item["line_total"] = float(item["base_price"]) * int(
                        item.get("quantity", 1)
                    )

            calculated_total = round(
                sum(
                    float(item.get("line_total")) - float(item.get("discount_applied"))
                    for item in structured_data["items"]
                ),
                2,
            )

            for item in structured_data["items"]:
                bp = float(item.get("base_price", item.get("unit_price", 0)))
                da = float(item.get("discount_applied", 0))

                item["base_price"] = bp
                item["unit_price"] = round(bp - da, 2)
                item["loyalty_price"] = round(bp - da, 2) if da > 0 else None
                item["discount_type"] = item.get("discount_type", None)

            extracted_total = structured_data.get("total")

            if not extracted_total:
                logger.warning(
                    f"⚠️ Total missing. Injecting calculated sum: {calculated_total}"
                )
                structured_data["total"] = calculated_total
            elif abs(float(extracted_total) - calculated_total) > 0.01:
                deviation = abs(float(extracted_total) - calculated_total)

                if calculated_total > 0 and deviation < 2.00:
                    logger.warning(
                        f"⚠️ Minor Arithmetic mismatch (Extracted: {extracted_total}, Calculated: {calculated_total}). Trusting Python calculation over LLM extraction."
                    )
                    structured_data["total"] = calculated_total
                elif deviation > 2.00:
                    if calculated_total > float(extracted_total):
                        logger.error(
                            f"🚨 MASSIVE deviation (Extracted: {extracted_total}, Calculated: {calculated_total}). LLM likely missed discounts. Trusting extracted total."
                        )
                    elif float(extracted_total) > (calculated_total * 3) or (
                        calculated_total < 5.00 and deviation > 2.00
                    ):
                        logger.error(
                            f"🚨 MASSIVE deviation (Extracted: {extracted_total}, Calculated: {calculated_total}). Extracted total is suspiciously large. Trusting calculated sum."
                        )
                        structured_data["total"] = calculated_total
                    else:
                        logger.error(
                            f"🚨 MASSIVE deviation (Extracted: {extracted_total}, Calculated: {calculated_total}). OCR dropped item prices. Trusting extracted total."
                        )
                else:
                    logger.warning(
                        f"⚠️ Arithmetic mismatch! Extracted: {extracted_total}, Calculated: {calculated_total}. Trusting extracted total."
                    )

            logger.info("----- OCR COMPLETE (STRAT: STRUCTURED AI) -----")
            logger.info(
                f"Store: {structured_data.get('store_name')} | Date: {structured_data.get('date')} | Items Resolved: {len(structured_data['items'])} | Total Cost: {structured_data.get('total')}"
            )
            return structured_data

        logger.warning("⚠️ AI layer unaligned. Triggering regex structure fallback...")
        return extract_receipt_data_fallback(lines, full_text_dump)

    except Exception as e:
        logger.error(f"OCR ERROR: {str(e)}", exc_info=True)
        return {"store_name": "Unknown", "items": [], "total": None, "date": None}
