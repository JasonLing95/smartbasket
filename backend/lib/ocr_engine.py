# lib/ocr_engine.py
from __future__ import annotations
import os
import json
import re
import math
import statistics
import easyocr
import logging
from groq import Groq

logger = logging.getLogger(__name__)

# Initialize globally
try:
    import easyocr

    # Initialize your local reader if available
    reader = easyocr.Reader(["en"], gpu=False)
except ImportError:
    # Fallback context for production serverless instances
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
]

PRICE_PATTERN = re.compile(r"([£€E]?\s*\d+[\.,]\s*\d{2})", re.IGNORECASE)


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
    """Groups text using a tight Center-to-Center anchor to prevent vertical line collisions."""
    lines_data = []

    for bbox, text, _ in results:
        # Calculate the vertical center point and height of the current word
        y_center = (bbox[0][1] + bbox[2][1]) / 2
        word_height = bbox[2][1] - bbox[0][1]

        placed = False
        for line in lines_data:
            # Calculate the average Y-center of the existing line
            line_y_centers = [(item[0][0][1] + item[0][2][1]) / 2 for item in line]
            avg_line_y_center = sum(line_y_centers) / len(line_y_centers)

            # TIGHTER ZONE: The word's center must be closely aligned with the line's center
            if abs(y_center - avg_line_y_center) <= (word_height * 0.35):
                line.append((bbox, text))
                placed = True
                break

        if not placed:
            lines_data.append([(bbox, text)])

    # Sort lines top to bottom based on their center points
    lines_data.sort(
        key=lambda line: sum((item[0][0][1] + item[0][2][1]) / 2 for item in line)
        / len(line)
    )

    final_lines = []
    for line in lines_data:
        # Sort words left to right
        line.sort(key=lambda x: x[0][0][0])
        final_lines.append(" ".join(text for _, text in line))

    return final_lines


def extract_receipt_data_via_llm(text_blob: str) -> dict | None:
    """
    Leverages the structural contextual processing capacity of Llama 3 to split
    multi-buy line items into canonical quantities and individual unit prices.
    """
    if not groq_client:
        logger.warning("Groq client not initialized. Skipping LLM extraction.")
        return None

    system_instruction = (
        "You are an advanced retail receipt intelligence document parser built specifically for UK supermarkets.\n"
        "Analyze the provided raw text lines extracted from a grocery receipt and convert them into a clean structured JSON format.\n\n"
        "Rules:\n"
        "1. Identify the store_name cleanly (e.g. Tesco, Sainsbury's, Co-op, Lidl, Aldi, Morrisons).\n"
        "2. CRITICAL - SCREENSHOT METADATA BAN: Completely ignore mobile phone status bar indicators.\n"
        "3. CRITICAL - LOYALTY DISCOUNTS & MEAL DEALS: Discounts apply to the parent item ABOVE them. Capture the positive base price in 'base_price', and the absolute value of the discount in 'discount_applied' (e.g., 0.50). Determine the name of the discount program (e.g., 'Tesco Clubcard', 'Nectar Price', 'Meal Deal') and output it as 'discount_type'. If there is no discount, set discount_type to null.\n"
        "4. CRITICAL - MULTI-LINE PRODUCTS & PRICE ANCHORING: Collapse consecutive rows of a single product into ONE entry. If an item description wraps to a second line (e.g., 'Walkers Crisps' on line 1, 'Sweet Chilli 150g' on line 2), DO NOT split them into two items. Ensure you lock the base_price to the EXACT positive number printed on the extreme right of the parent item's row. Never mistake a negative discount amount or promotional text (like 'Cc £1.65') for a base unit price.\n"
        "5. CRITICAL - DATE EXTRACTION: Extract the exact printed transaction date. You MUST assume all dates are printed in standard UK format (DD/MM/YY or DD/MM/YYYY). Convert the extracted date strictly to YYYY-MM-DD. For example, '02/06/26' must become '2026-06-02'.\n"
        "6. CRITICAL - QUANTITY MULTIPLIERS & LEADING INTEGERS: Look for inline multipliers (e.g., '5 x £1.75') OR leading standalone integers at the very start of a line (e.g., '2 M SPINACH' means quantity 2). You MUST extract the exact quantity AND completely remove that leading integer and any multiplier symbols from the final 'raw_string' output (e.g., output 'M SPINACH', not '2 M SPINACH').\n"
        "7. CRITICAL - EXTENDED TAX LETTERS & OCR MUTATIONS: UK supermarkets append tax letters (A, B, C, D, E, F, V, or *) to the far right. Ignore them. WARNING: OCR frequently misreads 'F' as '5' or '8', 'B' as '8', and 'A' as '4'. DISCARD THESE.\n"
        "8. CRITICAL - OCR NOISE & THE '8' MUTATION: OCR heavily misreads the '£' symbol as the number '8', leading to inflated prices (e.g., OCR reads '£5.50' as '85.50', or '£9.20' as '89.20'). Single grocery items rarely cost over £20. If you see a price starting with an 8 (e.g., 8X.XX), you MUST assume the leading '8' is a mangled '£' sign. Drop the '8' and extract the remaining float (e.g., '85.50' becomes 5.50, '89.20' becomes 9.20). Strip all other currency characters.\n"
        "9. CRITICAL - DUAL PRICE COLUMNS & LINE TOTALS: If you see BOTH a Unit Price and a Line Total on the same row (e.g., '5 x £1.75 8.75'), you MUST extract the smaller unit price (£1.75) as the 'base_price', and the explicit final larger amount (£8.75) as the 'line_total'. Do NOT ignore the line total."
        "10. CRITICAL - TOTAL EXTRACTION vs PAYMENT METHODS: Extract the final net total cost of the basket. This is usually labeled 'BALANCE DUE', 'TOTAL', or 'AMOUNT DUE'. You MUST explicitly ignore any lines detailing how the customer paid (e.g., 'GIFT CARD', 'CASH', 'CREDIT/DEBIT', 'VISA', 'MASTERCARD'). Never extract a partial payment or tender amount as the total.\n"
        "11. CRITICAL - WEIGHED PRODUCE / MEAT UNITS: When loose produce or meat is sold by weight, the receipt will often span multiple lines, listing a weight or unit rate first, followed by the actual final price paid on the next line or on the extreme right (e.g., '0.450 kg @ £1.50/kg \n LOOSE BANANAS £0.68'). You MUST extract the actual final amount paid (£0.68) as the net base_price, and set the quantity strictly to 1. NEVER use the weight rate (£1.50) as the price.\n"
        "12. CRITICAL - VOIDS, CANCELLATIONS, & REFUNDS: If an item was scanned by mistake and subsequently removed by the cashier, it will appear with a 'VOID', 'LESS', or '-' prefix or suffix, alongside a negative value (e.g., 'VOID - JS LARGE GARLIC -£0.50'). You MUST match this voided line to the original positive entry above it and decrease that item's quantity or remove it entirely. NEVER output a standalone item with a negative base_price or a negative quantity.\n"
        "13. CRITICAL - THE VOLUME/WEIGHT TRAP: Supermarket items often contain volume or weight metrics in the name (e.g., '1.75L', '500g', '1KG', '2.5L'). NEVER extract these numbers as the base_price. Ignore any float attached to a metric unit and look further right for the actual currency price.\n"
        "Expected Output Schema Example:\n"
        "{\n"
        '  "store_name": "Morrisons",\n'
        '  "date": "2025-12-24",\n'
        '  "total": 11.00,\n'
        '  "items": [\n'
        '    {"raw_string": "Spinach", "base_price": 2.25, "line_total": 4.50, "discount_applied": 0.50, "discount_type": "More Card", "quantity": 2}\n'
        "  ]\n"
        "}"
    )

    try:
        logger.info("Sending text blob to Groq LLM for structural parsing...")
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Raw Receipt Text Lines:\n{text_blob}"},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed_data = json.loads(completion.choices[0].message.content)
        logger.debug(f"LLM Raw Output: {json.dumps(parsed_data)}")
        return parsed_data
    except Exception as e:
        logger.error(f"Groq intelligent document parser error: {e}", exc_info=True)
        return None


def extract_receipt_data_fallback(lines, text_blob: str):
    store_name = detect_store(text_blob)
    items = []
    for line in lines:
        if any(word in line.lower() for word in STOPWORDS):
            continue
        match = PRICE_PATTERN.search(line)
        if match:
            # Clean out currency characters (including misread text prefixes like E, e, or €)
            clean_price_str = re.sub(r"[£€Ee\s]", "", match.group(1)).replace(",", ".")
            try:
                price = float(clean_price_str)
                desc = line[: match.start()].strip()
                if len(desc) > 2 and not desc.isdigit():
                    items.append(
                        {"raw_string": desc, "unit_price": price, "quantity": 1}
                    )
            except ValueError:
                # Discard misread structural rows safely without interrupting backend processing context
                continue

    return {
        "store_name": store_name,
        "items": items,
        "total": round(sum(i["unit_price"] for i in items), 2),
        "date": None,
    }


def extract_receipt_data(file_bytes: bytes):
    """
    Core parsing script. Processes raw bytes from an image
    and outputs a structured dictionary.
    """
    if reader is None:
        # Fallback block used strictly when deployed to Vercel Serverless
        logger.warning(
            "Executing in Lean Production Web Layer. Direct OCR execution disabled."
        )
        return {}

    logger.info("Executing heavy EasyOCR sequence...")
    try:
        logger.info("----- OCR START -----")
        results = reader.readtext(file_bytes, detail=1)

        straightened_results = deskew_positions(results)
        text_blob = "\n".join(text for _, text, _ in straightened_results)
        lines = group_into_lines(straightened_results)
        full_text_dump = "\n".join(lines)

        logger.info(f"Raw Extracted Text Length: {len(full_text_dump)} chars")
        logger.debug(f"Raw Extracted Text Dump:\n{full_text_dump}")

        structured_data = extract_receipt_data_via_llm(full_text_dump)

        if structured_data and "items" in structured_data:
            # Clean out any empty stubs or garbage lines before running math
            structured_data["items"] = [
                item
                for item in structured_data["items"]
                if item.get("raw_string") and item["raw_string"].strip() != ""
            ]

            # If no valid items remain, fallback immediately
            if not structured_data["items"]:
                logger.warning(
                    "⚠️ AI returned no valid items. Triggering regex structure fallback..."
                )
                return extract_receipt_data_fallback(lines, text_blob)

            for item in structured_data["items"]:
                if item.get("base_price") is None:
                    # If base_price is null, try to reverse-engineer it from the line_total
                    if item.get("line_total") is not None and item.get("quantity"):
                        item["base_price"] = float(item["line_total"]) / int(
                            item["quantity"]
                        )
                    else:
                        item["base_price"] = 0.0

                # Ensure discount is never None
                if item.get("discount_applied") is None:
                    item["discount_applied"] = 0.0

                # Ensure line_total is never None (fallback to base * qty)
                if item.get("line_total") is None:
                    item["line_total"] = float(item["base_price"]) * int(
                        item.get("quantity", 1)
                    )

            # Now the math will execute safely because no value can possibly be None
            calculated_total = round(
                sum(
                    float(item.get("line_total")) - float(item.get("discount_applied"))
                    for item in structured_data["items"]
                ),
                2,
            )

            # Assign the calculated net prices back to the item for the database
            for item in structured_data["items"]:
                bp = float(item.get("base_price", item.get("unit_price", 0)))
                da = float(item.get("discount_applied", 0))

                item["base_price"] = bp
                item["unit_price"] = round(bp - da, 2)  # Keep for legacy compatibility
                item["loyalty_price"] = round(bp - da, 2) if da > 0 else None
                item["discount_type"] = item.get("discount_type", None)

            extracted_total = structured_data.get("total")

            if not extracted_total:
                logger.warning(
                    f"⚠️ Total missing. Injecting calculated sum: {calculated_total}"
                )
                structured_data["total"] = calculated_total
            elif abs(float(extracted_total) - calculated_total) > 0.01:
                if abs(float(extracted_total) - calculated_total) > 5.00:
                    if calculated_total > float(extracted_total):
                        logger.error(
                            f"🚨 MASSIVE deviation (Extracted: {extracted_total}, Calculated: {calculated_total}). LLM likely missed discounts. Trusting extracted total."
                        )
                    else:
                        logger.error(
                            f"🚨 MASSIVE deviation (Extracted: {extracted_total}, Calculated: {calculated_total}). Likely OCR failure on the Total. Trusting calculated sum."
                        )
                        structured_data["total"] = calculated_total
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
        return extract_receipt_data_fallback(lines, text_blob)

    except Exception as e:
        logger.error(f"OCR ERROR: {str(e)}", exc_info=True)
        return {"store_name": "Unknown", "items": [], "total": None, "date": None}
