# lib/matcher.py
from __future__ import annotations
from lib.db import execute_query


def find_canonical_item(
    raw_string: str, similarity_threshold: float = 0.65
) -> dict | None:
    """Attempts a strict match, falling back immediately to an indexed database
    trigram similarity check to handle typos and word truncations safely.
    """
    cleaned_string = raw_string.strip()
    if not cleaned_string:
        return None

    # 1. Tier 1: Look for an exact match against historical messy entries
    strict_query = """
        SELECT master_item_id 
        FROM price_history 
        WHERE raw_name = %s 
        LIMIT 1;
    """
    res = execute_query(strict_query, (cleaned_string,))
    if res:
        return {"master_item_id": str(res[0][0]), "match_method": "strict_cache"}

    # 2. Tier 2: Trigram similarity fallback (The Aurora Performance Win)
    # This matches "Red Seedless Grap" straight to "Red Seedless Grape"
    # FIX: Escaped the literal trigram '%' operator as '%%' for psycopg2 compatibility
    fuzzy_query = """
        SELECT master_item_id, similarity(raw_name, %s) as score
        FROM price_history
        WHERE raw_name %% %s  -- Filters rows matching the similarity threshold
        ORDER BY score DESC
        LIMIT 1;
    """
    res = execute_query(fuzzy_query, (cleaned_string, cleaned_string))

    if res and res[0][1] >= similarity_threshold:
        return {
            "master_item_id": str(res[0][0]),
            "match_method": "fuzzy_trigram",
        }

    return None
