"""
Match parsed food items against the foods database.

Strategy:
1. Exact name match (case-insensitive)
2. Substring containment on name and aliases
3. Token overlap (word-level)
4. Fuzzy match via thefuzz if available (score >= FUZZY_THRESHOLD)

Returns the best single match or None.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from app.models import Food

FUZZY_THRESHOLD = 75  # minimum fuzz score (0–100)

try:
    from thefuzz import fuzz as _fuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    _FUZZY_AVAILABLE = False


def _all_names(food: Food) -> list[str]:
    """Return the food's name plus all alias variants."""
    names = [food.name]
    names.extend(food.alias_list())
    return names


def _token_overlap(query: str, candidate: str) -> int:
    """Return the number of query words present in the candidate."""
    q_tokens = set(query.lower().split())
    c_tokens = set(candidate.lower().split())
    return len(q_tokens & c_tokens)


def find_match(query: str, db: Session) -> Food | None:
    """
    Return the best matching Food for *query*, or None.
    """
    query = query.strip().lower()
    if not query:
        return None

    all_foods = db.query(Food).all()

    # 1. Exact match
    for food in all_foods:
        if query in [n.lower() for n in _all_names(food)]:
            return food

    # 2. Containment — query is a substring of a stored name or vice-versa
    containment_hits: list[tuple[Food, int]] = []
    for food in all_foods:
        for name in _all_names(food):
            n = name.lower()
            if query in n or n in query:
                # prefer longer overlap
                containment_hits.append((food, len(set(query.split()) & set(n.split()))))
                break

    if containment_hits:
        return max(containment_hits, key=lambda x: x[1])[0]

    # 3. Token overlap
    token_hits: list[tuple[Food, int]] = []
    for food in all_foods:
        best = max(_token_overlap(query, n) for n in _all_names(food))
        if best > 0:
            token_hits.append((food, best))

    if token_hits:
        best_food, best_score = max(token_hits, key=lambda x: x[1])
        if best_score >= max(1, len(query.split()) // 2):
            return best_food

    # 4. Fuzzy (optional)
    if _FUZZY_AVAILABLE:
        fuzzy_hits: list[tuple[Food, int]] = []
        for food in all_foods:
            score = max(_fuzz.token_set_ratio(query, n.lower()) for n in _all_names(food))
            if score >= FUZZY_THRESHOLD:
                fuzzy_hits.append((food, score))
        if fuzzy_hits:
            return max(fuzzy_hits, key=lambda x: x[1])[0]

    return None
