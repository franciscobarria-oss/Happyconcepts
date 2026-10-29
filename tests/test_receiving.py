import pytest

from happy_kitchen.recipe_management import receiving as r


def test_exact_delivery_has_no_flags():
	assert r.line_flags(10, 10, 5.0, 5.0) == []
	assert r.line_flags(10, 10, 5.0, None) == []


def test_short_over_and_missing():
	assert r.line_flags(10, 7, 5, None) == ["short 3"]
	assert r.line_flags(10, 12, 5, None) == ["over 2"]
	assert r.line_flags(10, 0, 5, None) == ["not delivered"]


def test_price_change_beyond_tolerance():
	assert r.line_flags(10, 10, 100, 104) == ["price +4.0%"]
	assert r.line_flags(10, 10, 100, 97) == ["price -3.0%"]
	assert r.line_flags(10, 10, 100, 100.4) == []  # within 0.5%
	assert r.line_flags(10, 10, 100, 100.4, price_tolerance_pct=0) == ["price +0.4%"]


def test_short_and_dearer_together():
	assert r.line_flags(10, 8, 100, 110) == ["short 2", "price +10.0%"]


def test_delivery_summary():
	s = r.delivery_summary([
		{"item": "FLOUR", "ordered_qty": 20, "received_qty": 20, "po_rate": 160, "invoice_rate": 160},
		{"item": "EGG", "ordered_qty": 360, "received_qty": 300, "po_rate": 0.83, "invoice_rate": 0.9},
	])
	assert s["flagged_lines"] == 1 and s["has_discrepancy"]
	assert s["lines"][1]["flags"] == ["short 60", "price +8.4%"]
	assert s["received_value"] == pytest.approx(20 * 160 + 300 * 0.83)  # at the ordered price
