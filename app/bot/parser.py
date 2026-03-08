"""
Parse natural language food messages into structured items.

Examples
--------
"2 eggs on toast"              -> [ParsedItem("2 eggs on toast", qty=2, ...)]
"coffee with milk, banana"     -> [ParsedItem("coffee with milk"), ParsedItem("banana")]
"lunch: chicken salad, roll"   -> [ParsedItem("chicken salad", meal="lunch"), ...]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Meal labels we recognise
MEAL_LABELS = {"breakfast", "lunch", "dinner", "supper", "snack", "brunch"}

# Tokens that join items in a single message
SPLIT_PATTERN = re.compile(r"\s*,\s*|\s+and\s+|\n", re.IGNORECASE)

# Quantity patterns like "2", "2x", "two", "half", "a", "an"
WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "half": 0.5, "quarter": 0.25,
}
QTY_PATTERN = re.compile(
    r"^(?P<qty>\d+(?:\.\d+)?x?|half|quarter|a(?:n)?|one|two|three|four|five|"
    r"six|seven|eight|nine|ten)\s+",
    re.IGNORECASE,
)


@dataclass
class ParsedItem:
    raw: str           # original text fragment
    name: str          # cleaned food name
    quantity: float = 1.0
    meal: str | None = None
    extra: dict = field(default_factory=dict)


def _extract_quantity(text: str) -> tuple[float, str]:
    """Return (quantity, remaining_text)."""
    m = QTY_PATTERN.match(text.strip())
    if not m:
        return 1.0, text.strip()
    qty_str = m.group("qty").lower().rstrip("x")
    qty = WORD_NUMBERS.get(qty_str, None)
    if qty is None:
        try:
            qty = float(qty_str)
        except ValueError:
            qty = 1.0
    remaining = text[m.end():].strip()
    return qty, remaining


def _extract_meal_label(text: str) -> tuple[str | None, str]:
    """If text starts with 'meal:', extract and strip the label."""
    m = re.match(r"^(\w+)\s*:\s*", text.strip(), re.IGNORECASE)
    if m and m.group(1).lower() in MEAL_LABELS:
        return m.group(1).lower(), text[m.end():].strip()
    return None, text.strip()


def parse_message(text: str) -> list[ParsedItem]:
    """Parse a user message into a list of ParsedItems."""
    text = text.strip()

    # Extract leading meal label, e.g. "lunch: ..."
    meal_label, text = _extract_meal_label(text)

    # Split on commas, "and", newlines
    fragments = SPLIT_PATTERN.split(text)

    items: list[ParsedItem] = []
    for fragment in fragments:
        fragment = fragment.strip()
        if not fragment:
            continue

        # Each fragment might also carry its own meal label
        item_meal, fragment = _extract_meal_label(fragment)
        effective_meal = item_meal or meal_label

        qty, name = _extract_quantity(fragment)
        name = name.lower().strip()

        if name:
            items.append(ParsedItem(raw=fragment, name=name, quantity=qty, meal=effective_meal))

    return items
