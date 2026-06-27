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


def resolve_unmatched_entity(
    raw_string: str,
    discount_type: str = None,
    candidate_items: list = None,  # List of dicts: [{"id": "...", "name": "...", "category": "..."}]
    available_categories: list = None,
) -> dict:
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

    if not candidate_items:
        candidate_items = []
    if not available_categories:
        available_categories = ["Groceries"]

    candidates_text = (
        "\n".join(
            [
                f"- ID: {c['id']}, Name: '{c['name']}', Category: {c['category']}"
                for c in candidate_items
            ]
        )
        if candidate_items
        else "No close matches found in catalog."
    )

    categories_text = ", ".join(available_categories)

    system_instruction = (
        "You are a strict product-matching AI. Your task is to decide if the given product name "
        "already exists in our catalog, or if we need to create a new entry.\n\n"
        "### CATALOG CATEGORIES (You MUST choose one of these exact strings for 'category'):\n"
        f"{categories_text}\n\n"
        "### CLOSEST EXISTING CATALOG ITEMS (Potential Matches):\n"
        f"{candidates_text}\n\n"
        "### RULES:\n"
        "1. **Prefer Matching**: If the input product is semantically identical to one of the 'Closest Existing Catalog Items' (e.g., singular vs plural, minor typos like 'Grap' vs 'Grapes', or missing descriptive words like 'Organic'), you MUST return `action: 'match'` and provide the exact `matched_item_id`.\n"
        "2. **Create New Only**: Only return `action: 'create'` if the product is genuinely distinct (e.g., 'Coca-Cola' vs 'Pepsi', or 'Whole Milk' vs 'Skimmed Milk').\n"
        "3. **Category Enforcement**: If you choose `create`, you MUST select the `category` from the provided Catalog Categories list. Do not invent new categories.\n"
        "4. **Size Extraction**: Extract `size_value` (float) and `size_unit` (string: g, kg, L, ml) if present.\n\n"
        "### OUTPUT JSON SCHEMA (Strict):\n"
        "{\n"
        '  "action": "match" | "create",\n'
        '  "matched_item_id": "uuid-string" | null,  // Required if action == "match"\n'
        '  "cleaned_name": "Final product name",     // The best human-readable name\n'
        '  "category": "Exact Category String",      // Required if action == "create"\n'
        '  "size_value": 400.0 | null,\n'
        '  "size_unit": "g" | null\n'
        "}\n\n"
        "Input Product: '{raw_string}'"
        + (f"\nContextual Discount Hint: '{discount_type}'" if discount_type else "")
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
        action = ai_payload.get("action")
        cleaned_name = ai_payload.get("cleaned_name", "").strip()

        if not cleaned_name or action == "skip":  # keep your skip logic
            return {"action": "skip"}

        # If the LLM picked an existing ID from the candidates
        if action == "match" and ai_payload.get("matched_item_id"):
            logger.info(
                f"🤖 AI selected existing item: {ai_payload['matched_item_id']}"
            )
            return {
                "action": "match",
                "matched_item_id": ai_payload["matched_item_id"],
                "cleaned_name": cleaned_name,
                "category": ai_payload.get("category"),
                "size_value": ai_payload.get("size_value"),
                "size_unit": ai_payload.get("size_unit"),
            }

        # If the LLM decided to create a new one
        elif action == "create":
            category = ai_payload.get("category", "Groceries")
            # Ensure it chose from our strict list
            if category not in available_categories:
                logger.warning(
                    f"LLM chose '{category}' which is not in taxonomy. Defaulting to 'Groceries'."
                )
                category = "Groceries"

            return {
                "action": "create",
                "matched_item_id": None,
                "cleaned_name": cleaned_name,
                "category": category,
                "size_value": ai_payload.get("size_value"),
                "size_unit": ai_payload.get("size_unit"),
            }

        return {"action": "skip"}

    except Exception as e:
        logger.error(f"Groq runtime resolution failure: {e}", exc_info=True)
        return {"action": "skip"}
