"""Parsing and formatting of money amounts."""


def to_cents(amount: str) -> int:
    """Parse a decimal string such as '19.99' or '-3.5' into integer cents."""
    return int(float(amount) * 100)


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
