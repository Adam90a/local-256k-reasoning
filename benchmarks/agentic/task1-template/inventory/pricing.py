"""Pricing rules. All money is integer cents."""
from .models import Item

# Discount per category, in PERCENT (e.g. 15 means 15% off).
CATEGORY_DISCOUNT_PCT = {"clearance": 40, "seasonal": 15, "general": 0}


def discounted_unit_price(item: Item) -> int:
    pct = CATEGORY_DISCOUNT_PCT.get(item.category, 0)
    # Bug: treats the percent as a fraction, so any discount wipes the price out.
    return round(item.unit_price_cents * (1 - pct))


def line_total(item: Item) -> int:
    return discounted_unit_price(item) * item.quantity
