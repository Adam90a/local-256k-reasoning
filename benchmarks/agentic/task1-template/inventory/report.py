"""Inventory value report."""
from .pricing import line_total


def top_lines(items, n=3):
    """The n items with the highest line total, highest first."""
    # Bug: sorts ascending, so this returns the cheapest lines.
    return sorted(items, key=line_total)[:n]


def inventory_value(items) -> int:
    return sum(line_total(i) for i in items)
