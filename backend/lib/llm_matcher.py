# lib/llm_matcher.py
from __future__ import annotations
import os
import re
import json
import logging
from groq import Groq
from lib.db import execute_query

logger = logging.getLogger(__name__)

# Initialize the Groq client
groq_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=groq_key) if groq_key else None


def resolve_unmatched_entity(raw_string: str, discount_type: str = None) -> dict:
    """Leverages Groq to semantic-clean an unrecognized receipt string, grouping variation variants."""
    if not raw_string or not raw_string.strip():
        return {"action": "skip"}

    # --- 🛡️ HARD PYTHON JUNK SHIELD 🛡️ ---
    letter_count = len(re.sub(r"[^A-Za-z]", "", raw_string))
    if len(raw_string.strip()) < 8 and letter_count <= 2:
        logger.info(f"🛡️ Python Regex Guard blocked junk fragment: '{raw_string}'")
        return {"action": "skip"}
    # ------------------------------------------

    if not client:
        logger.warning(
            "⚠️ Groq API key missing from environment variables. Skipping AI layer."
        )
        return {"action": "skip"}

    system_instruction = (
        "You are an expert data engineer specializing in retail product text sanitization and string alignment.\n"
        "Your task is to analyze a messy, raw grocery receipt item string and normalize it into a clean, human-readable product name.\n"
        "Strip away internal retail store tracking codes, random punctuation errors, and purchase quantities.\n\n"
        "CRITICAL: You must return absolutely nothing except a valid JSON object matching this exact schema:\n"
        "{\n"
        '  "cleaned_name": "The stripped human-readable product name (capitalized words, no junk values)",\n'
        '  "category": "Department Name",\n'
        '  "size_value": 400.0,  // Extract the numeric volume/weight. Return null if none.\n'
        '  "size_unit": "g"      // Extract the unit (e.g., g, kg, L, ml). Return null if none.\n'
        "}\n\n"
        "Rules:\n"
        "1. PREFIX CLEANING & SIZING: Strip store prefixes. Extract any weight or volume into the separate 'size_value' and 'size_unit' fields. DO NOT append the weight to the 'cleaned_name'.\n"
        "2. JUNK/FRAGMENT RULE: If the raw string contains no recognizable product description, consists only of numbers, or is a solitary tax letter... you MUST return an empty string for both fields to trigger a pipeline skip.\n"
        "3. STRIP SUPERMARKET BRAND JARGON: Completely remove retail tier prefixes, brand markers, and internal abbreviations from the final name (e.g., Strip 'JS', 'SSTC', 'SO', 'M', 'WM', 'HBR').\n"
        "4. AGGRESSIVE OCR HEALING: OCR engines frequently misread characters or insert symbols into valid dictionary words (e.g., 'A Imonds', 'Hatura1', 'Hinera]', 'Stf1I'). You MUST aggressively heal these typographical errors to their closest logical grocery term ('Almonds', 'Natural', 'Mineral', 'Still'). However, do NOT over-correct intentional brand puns or well-known stylized spellings (e.g., 'Biotiful' is a real brand, do not change it to 'Beautiful').\n"
        "5. PRESERVE CORE NOUNS: Your job is to clean, not rewrite. If you encounter a mangled word (e.g., 'HuSHROOHS'), you may correct the spelling (e.g., 'Mushrooms'). You MUST NEVER combine words, delete the primary descriptive noun, or invert modifiers (e.g., 'Seedles Grap' MUST become 'Seedless Grapes', NEVER 'Grapeseed').\n"
        "6. CATEGORY HALLUCINATION PREVENTION: Do not guess highly specific categories (like 'Meat' or 'Seafood') if the text is just a fragmented brand, country, or ambiguous adjective (e.g., 'Spanish', 'Finest'). Default to 'Groceries' or 'Miscellaneous'.\n"
        "7. ALCOHOL IDENTIFIERS: If you see words like 'Dry', 'Res', 'Blanc', or 'Pnt' associated with a country (e.g., 'Spanish Dry', 'French Blanc'), categorize it strictly as 'Alcohol' or 'Wine'.\n"
        "8. CONTEXTUAL HINTS: If a 'Contextual Hint' is provided (e.g., a wine discount, a meal deal), use it to determine the category if the raw string is ambiguous. For example, if the string is 'SPANISH Pr' and the hint is 'Co-op Wine Offer', you must classify it as 'Wine' or 'Alcohol'.\n\n"
        "9. MASHED WORDS & PASCALCASE: Discount supermarkets often print items with no spaces (e.g., 'ChewingGumWhiteMint', 'FreshMilkSemi'). You MUST split these mashed words into properly spaced, human-readable terms, even if OCR has slightly mangled the letters within them (e.g., 'ChewingGumlhitel Int' MUST be split and healed into 'Chewing Gum White Mint').\n\n"
        "Examples of messy raw string translations:\n"
        "- 'JS STRAWBS 40OG' -> Cleaned: 'Strawberries', Category: 'Fresh Produce', size_value: 400.0, size_unit: 'g'\n"
        "- 'SHRNEBS HooG' -> Cleaned: 'Strawberries', Category: 'Fresh Produce', size_value: 400.0, size_unit: 'g'\n"
        "- 'Coca cola (original Taste) 1.75l' -> Cleaned: 'Coca-Cola Original Taste', Category: 'Beverages', size_value: 1.75, size_unit: 'L'\n"
        "- 'Org Bnz 1kg Swt' -> Cleaned: 'Organic Bananas', Category: 'Fresh Produce', size_value: 1.0, size_unit: 'kg'\n"
        "- 'Ktc Pure Butter Ghee 500g' -> Cleaned: 'Pure Butter Ghee', Category: 'Dairy', size_value: 500.0, size_unit: 'g'\n"
        "- '1 Red Seedles Gr ap' -> Cleaned: 'Red Seedless Grapes', Category: 'Fresh Produce', size_value: null, size_unit: null\n"
        "- 'Stf1I Hinera] Water' -> Cleaned: 'Still Mineral Water', Category: 'Beverages', size_value: null, size_unit: null\n"
        "- 'Graham\\'s Hatura1' -> Cleaned: 'Grahams Natural', Category: 'Dairy', size_value: null, size_unit: null\n"
        "- 'ChewingGumlhitel Int' -> Cleaned: 'Chewing Gum White Mint', Category: 'Groceries', size_value: null, size_unit: null\n"
        "- 'biOTIfUL Kefir' -> Cleaned: 'Biotiful Kefir', Category: 'Dairy', size_value: null, size_unit: null\n"
    )

    logger.info(
        f"🔍 Matcher Input: Evaluating raw token: '{raw_string}' (Discount Hint Context: {discount_type})"
    )

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": f"Raw Receipt Line Entry to Process:\n'{raw_string}'"
                    + (
                        f"\nContextual Hint (Discount Program): '{discount_type}'"
                        if discount_type
                        else ""
                    ),
                },
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        ai_payload = json.loads(completion.choices[0].message.content)
        cleaned_name = ai_payload.get("cleaned_name", "").strip()
        category = ai_payload.get("category", "Miscellaneous").strip()
        category = category if category else "Miscellaneous"

        if not cleaned_name:
            logger.warning(
                f"⚠️ Matcher Output: AI elected to drop tracking fragment: '{raw_string}'"
            )
            return {"action": "skip"}

        logger.info(
            f"🎯 Matcher Output: Transformed '{raw_string}' -> '{cleaned_name}' (Assigned Category: {category})"
        )

        db_match = execute_query(
            "SELECT id, category FROM master_items WHERE canonical_name ILIKE %s LIMIT 1;",
            (cleaned_name,),
        )

        if db_match:
            decision = {
                "action": "match",
                "matched_item_id": str(db_match[0][0]),
                "cleaned_name": cleaned_name,
                "category": db_match[0][1],
                "size_value": ai_payload.get("size_value"),
                "size_unit": ai_payload.get("size_unit"),
            }
        else:
            decision = {
                "action": "create",
                "matched_item_id": None,
                "cleaned_name": cleaned_name,
                "category": category,
            }

        logger.info(f"🤖 AI/Python Hybrid Decision for '{raw_string}': {decision}")
        return decision

    except Exception as e:
        logger.error(f"Groq runtime resolution failure: {e}", exc_info=True)
        return {"action": "skip"}
