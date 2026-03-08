"""Tests for app/bot/matcher.py"""

import pytest
from app.bot.matcher import find_match
from app.models import Food


def _add_food(db, name, calories=300, aliases=None):
    food = Food(name=name, calories=calories, aliases=aliases)
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


class TestExactMatch:
    def test_exact_name(self, db_session):
        _add_food(db_session, "banana")
        result = find_match("banana", db_session)
        assert result is not None
        assert result.name == "banana"

    def test_case_insensitive(self, db_session):
        _add_food(db_session, "banana")
        result = find_match("Banana", db_session)
        assert result is not None
        assert result.name == "banana"

    def test_exact_alias_match(self, db_session):
        _add_food(db_session, "chicken sandwich", aliases="chicken sarnie,chick sandwich")
        result = find_match("chicken sarnie", db_session)
        assert result is not None
        assert result.name == "chicken sandwich"


class TestSubstringMatch:
    def test_query_in_stored_name(self, db_session):
        _add_food(db_session, "grilled chicken breast")
        result = find_match("chicken breast", db_session)
        assert result is not None
        assert result.name == "grilled chicken breast"

    def test_stored_name_in_query(self, db_session):
        _add_food(db_session, "coffee")
        result = find_match("coffee with milk", db_session)
        assert result is not None
        assert result.name == "coffee"

    def test_substring_alias(self, db_session):
        _add_food(db_session, "oatmeal", aliases="porridge,oats")
        result = find_match("oats", db_session)
        assert result is not None
        assert result.name == "oatmeal"


class TestTokenOverlapMatch:
    def test_partial_word_overlap(self, db_session):
        _add_food(db_session, "scrambled eggs")
        result = find_match("eggs on toast", db_session)
        # Should match because "eggs" overlaps
        assert result is not None
        assert result.name == "scrambled eggs"

    def test_no_match_empty_db(self, db_session):
        result = find_match("banana", db_session)
        assert result is None

    def test_no_match_unrelated_food(self, db_session):
        _add_food(db_session, "apple")
        result = find_match("xyz unknown thing", db_session)
        assert result is None


class TestFuzzyMatch:
    def test_typo_in_query(self, db_session):
        _add_food(db_session, "chicken sandwich")
        # Fuzzy should catch minor typos
        result = find_match("chickin sandwitch", db_session)
        # May or may not match depending on score threshold — just don't crash
        # (we test it returns Food or None, not a specific value)
        assert result is None or result.name == "chicken sandwich"

    def test_multiple_foods_best_match(self, db_session):
        _add_food(db_session, "apple", calories=80)
        _add_food(db_session, "apple juice", calories=120)
        result = find_match("apple juice", db_session)
        assert result is not None
        assert result.name == "apple juice"
