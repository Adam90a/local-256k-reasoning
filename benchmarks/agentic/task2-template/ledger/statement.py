"""Statement rendering."""
from .money import fmt


def paginate(entries, page: int, per_page: int = 10):
    start = page * per_page
    return entries[start:start + per_page]


def render(entries, page: int, per_page: int = 10) -> str:
    rows = [f"{e['date']}  {e['memo']:<20} {fmt(e['cents']):>10}" for e in paginate(entries, page, per_page)]
    return "\n".join(rows)
