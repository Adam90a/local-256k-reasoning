from inventory.models import Item
from inventory.pricing import discounted_unit_price, line_total
from inventory.report import top_lines, inventory_value

ITEMS = [
    Item("A1", "Widget", 1000, 3),                    # 3000
    Item("B2", "Gadget", 2500, 2, "seasonal"),        # 2125 * 2 = 4250
    Item("C3", "Gizmo", 800, 10, "clearance"),        # 480 * 10 = 4800
    Item("D4", "Doohickey", 150, 4),                  # 600
]


def test_no_discount():
    assert discounted_unit_price(ITEMS[0]) == 1000


def test_seasonal_discount():
    assert discounted_unit_price(ITEMS[1]) == 2125


def test_clearance_line_total():
    assert line_total(ITEMS[2]) == 4800


def test_inventory_value():
    assert inventory_value(ITEMS) == 3000 + 4250 + 4800 + 600


def test_top_lines():
    assert [i.sku for i in top_lines(ITEMS, 2)] == ["C3", "B2"]


def test_top_lines_default_n():
    assert len(top_lines(ITEMS)) == 3
