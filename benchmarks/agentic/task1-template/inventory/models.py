from dataclasses import dataclass


@dataclass
class Item:
    sku: str
    name: str
    unit_price_cents: int
    quantity: int
    category: str = "general"
