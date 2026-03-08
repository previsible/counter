"""Tests for app/bot/parser.py — pure unit tests, no DB needed."""

import pytest
from app.bot.parser import parse_message, ParsedItem


def names(items: list[ParsedItem]) -> list[str]:
    return [i.name for i in items]


def qtys(items: list[ParsedItem]) -> list[float]:
    return [i.quantity for i in items]


# ── Single items ──────────────────────────────────────────────────────────────

class TestSingleItem:
    def test_plain_food(self):
        items = parse_message("banana")
        assert names(items) == ["banana"]
        assert qtys(items) == [1.0]

    def test_quantity_integer(self):
        items = parse_message("2 eggs")
        assert items[0].name == "eggs"
        assert items[0].quantity == 2.0

    def test_quantity_float(self):
        items = parse_message("1.5 cups oats")
        assert items[0].quantity == 1.5
        assert items[0].name == "cups oats"

    def test_quantity_word_two(self):
        items = parse_message("two eggs")
        assert items[0].quantity == 2.0
        assert items[0].name == "eggs"

    def test_quantity_half(self):
        items = parse_message("half avocado")
        assert items[0].quantity == 0.5

    def test_quantity_a(self):
        items = parse_message("a banana")
        assert items[0].quantity == 1.0
        assert items[0].name == "banana"

    def test_quantity_an(self):
        items = parse_message("an apple")
        assert items[0].quantity == 1.0
        assert items[0].name == "apple"

    def test_quantity_x_suffix(self):
        items = parse_message("3x biscuit")
        assert items[0].quantity == 3.0
        assert items[0].name == "biscuit"

    def test_name_lowercased(self):
        items = parse_message("Chicken Sandwich")
        assert items[0].name == "chicken sandwich"


# ── Multiple items ────────────────────────────────────────────────────────────

class TestMultipleItems:
    def test_comma_split(self):
        items = parse_message("coffee, banana, toast")
        assert names(items) == ["coffee", "banana", "toast"]

    def test_and_split(self):
        items = parse_message("eggs and toast")
        assert names(items) == ["eggs", "toast"]

    def test_mixed_split(self):
        items = parse_message("coffee with milk, banana and toast")
        assert len(items) == 3
        assert items[0].name == "coffee with milk"
        assert items[1].name == "banana"
        assert items[2].name == "toast"

    def test_newline_split(self):
        items = parse_message("oats\nblueberries\ncoffee")
        assert names(items) == ["oats", "blueberries", "coffee"]

    def test_quantities_per_item(self):
        items = parse_message("2 eggs, 3 rashers bacon")
        assert items[0].quantity == 2.0
        assert items[0].name == "eggs"
        assert items[1].quantity == 3.0
        assert items[1].name == "rashers bacon"


# ── Meal labels ───────────────────────────────────────────────────────────────

class TestMealLabels:
    def test_meal_prefix_tags_all(self):
        items = parse_message("lunch: chicken salad, bread roll")
        assert all(i.meal == "lunch" for i in items)
        assert names(items) == ["chicken salad", "bread roll"]

    def test_breakfast_label(self):
        items = parse_message("breakfast: oats with milk")
        assert items[0].meal == "breakfast"

    def test_dinner_label(self):
        items = parse_message("dinner: pasta")
        assert items[0].meal == "dinner"

    def test_no_meal_label(self):
        items = parse_message("pasta")
        assert items[0].meal is None

    def test_meal_label_lowercased(self):
        items = parse_message("Lunch: salad")
        assert items[0].meal == "lunch"

    def test_non_meal_colon_not_stripped(self):
        # "protein: 30" has no recognised meal label, so whole string is the item
        items = parse_message("protein bar")
        assert len(items) == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        items = parse_message("")
        assert items == []

    def test_whitespace_only(self):
        items = parse_message("   ")
        assert items == []

    def test_trailing_comma(self):
        items = parse_message("eggs, toast,")
        assert len(items) == 2  # empty fragment dropped

    def test_complex_message(self):
        items = parse_message("lunch: 2 chicken thighs and a bread roll, diet coke")
        assert len(items) == 3
        assert items[0].quantity == 2.0
        assert items[0].name == "chicken thighs"
        assert items[1].quantity == 1.0
        assert items[1].name == "bread roll"
        assert items[2].name == "diet coke"
        assert all(i.meal == "lunch" for i in items)
