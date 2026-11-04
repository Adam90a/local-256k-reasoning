"""Currency conversion."""

RATES = {("USD", "EUR"): 0.9, ("EUR", "USD"): 1.1, ("USD", "JPY"): 150.25}


def convert(cents: int, src: str, dst: str) -> int:
    if src == dst:
        return cents
    rate = RATES[(src, dst)]
    return round(cents * rate)
