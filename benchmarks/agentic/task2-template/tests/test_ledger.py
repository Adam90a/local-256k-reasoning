from ledger.money import to_cents, fmt
from ledger.fx import convert
from ledger.statement import paginate, render

ENTRIES = [{"date": f"2026-03-{d:02d}", "memo": f"entry {d}", "cents": d * 100} for d in range(1, 26)]


def test_to_cents_simple():
    assert to_cents("12.00") == 1200


def test_to_cents_exact():
    assert to_cents("19.99") == 1999
    assert to_cents("0.29") == 29


def test_to_cents_negative():
    assert to_cents("-3.5") == -350


def test_fmt():
    assert fmt(-350) == "-3.50"


def test_convert_half_up():
    assert convert(5, "USD", "EUR") == 5        # 4.5 cents -> 5
    assert convert(25, "USD", "EUR") == 23      # 22.5 cents -> 23


def test_convert_jpy():
    assert convert(200, "USD", "JPY") == 30050


def test_first_page():
    assert [e["memo"] for e in paginate(ENTRIES, 1, 10)][0] == "entry 1"


def test_last_page_partial():
    assert len(paginate(ENTRIES, 3, 10)) == 5


def test_render_first_line():
    assert render(ENTRIES, 1).splitlines()[0].startswith("2026-03-01")
