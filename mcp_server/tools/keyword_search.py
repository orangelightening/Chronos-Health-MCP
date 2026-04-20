# SPDX-License-Identifier: MIT
#
"""
Keyword search tool for exact text matching.

Minimal implementation - contains matching only, case-insensitive.
"""
from typing import List, Dict


def keyword_search(chunks: List[Dict], keyword: str, case_sensitive: bool = False) -> List[Dict]:
    """
    Filter chunks by keyword matching (contains).

    Args:
        chunks: List of chunks to filter
        keyword: Keyword to search for
        case_sensitive: Whether to match case (default: False)

    Returns:
        List of matching chunks with match count
    """
    matches = []

    for chunk in chunks:
        text = chunk["text"]
        search_text = text if case_sensitive else text.lower()
        search_keyword = keyword if case_sensitive else keyword.lower()

        # Simple contains matching
        if search_keyword in search_text:
            # Count occurrences
            match_count = search_text.count(search_keyword)

            # Add match info to chunk
            chunk_with_match = chunk.copy()
            chunk_with_match["match_count"] = match_count
            matches.append(chunk_with_match)

    # Sort by match count (most matches first)
    matches.sort(key=lambda x: x["match_count"], reverse=True)

    return matches
