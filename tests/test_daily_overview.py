from datetime import date

from happy_kitchen.hk_operations.daily_overview import best_before, build_grid, column_for, group_spans

DAY = date(2026, 10, 24)


def test_column_from_xero_name():
	c = column_for({"name": "C1", "customer_name": "THE DAIRY FARM COMPANY LIMITED - CWB"})
	assert (c["group"], c["label"]) == ("IKEA", "CWB")
	c = column_for({"name": "C2", "customer_name": "SODEXO - SINGAPORE AIRLINE"})
	assert (c["group"], c["label"]) == ("SODEXO", "SA")
	c = column_for({"name": "C3", "customer_name": "W HOTEL"})
	assert (c["group"], c["label"]) == ("W HOTEL", "W HOTEL")


def test_column_fields_win():
	c = column_for({"name": "C3", "customer_name": "W HOTEL", "hk_sheet_group": "W Hotel",
	                "hk_sheet_label": "KLN W hotel", "hk_sheet_label_zh": "九龍 W Hotel", "hk_sheet_sort": 5})
	assert (c["group"], c["label"], c["label_zh"], c["sort"]) == ("W Hotel", "KLN W hotel", "九龍 W Hotel", 5)


def test_best_before():
	assert best_before(DAY, 4) == date(2026, 10, 28)
	assert best_before(DAY, 0) is None
	assert best_before(DAY, None) is None


def _lines():
	return [
		{"sales_order": "SO-1", "customer": "CWB", "item_code": "798815002", "qty": 20, "uom": "Nos", "po_no": "IFPO1", "so_grand_total": 100},
		{"sales_order": "SO-2", "customer": "CWB", "item_code": "798815002", "qty": 5, "uom": "Nos", "po_no": "IFPO2", "so_grand_total": 50},
		{"sales_order": "SO-3", "customer": "K11", "item_code": "798815002", "qty": 40, "uom": "Nos", "po_no": "IFPO3", "so_grand_total": 300},
		{"sales_order": "SO-3", "customer": "K11", "item_code": "RC009", "qty": 0, "uom": "Nos", "po_no": "IFPO3", "so_grand_total": 300},
		{"sales_order": "SO-4", "customer": "AMEX", "item_code": "SD008", "qty": 400, "uom": "Nos", "po_no": "HKPO9", "so_grand_total": 800},
	]


CUSTOMERS = {
	"CWB": {"name": "CWB", "customer_name": "THE DAIRY FARM COMPANY LIMITED - CWB"},
	"K11": {"name": "K11", "customer_name": "THE DAIRY FARM COMPANY LIMITED - K11"},
	"AMEX": {"name": "AMEX", "customer_name": "PLAZA PREMIUM LOUNGE HKG - AMEX"},
}
ITEMS = {"798815002": {"item_name": "Double choco", "item_name_zh": "雙重朱古力曲奇", "shelf_life_days": 4}}


def test_grid_cells_and_totals():
	g = build_grid(DAY, _lines(), CUSTOMERS, ITEMS)
	assert [c["label"] for c in g["columns"]] == ["CWB", "K11", "AMEX"]
	assert g["group_spans"] == [("IKEA", 2), ("PPL", 1)]
	by = {r["item_code"]: r for r in g["rows"]}
	assert set(by) == {"798815002", "SD008"}  # zero-qty line left out
	assert by["798815002"]["qtys"] == [25, 40, None]
	assert by["798815002"]["total"] == 65
	assert by["798815002"]["best_before"] == date(2026, 10, 28)
	assert by["SD008"]["best_before"] is None
	assert g["grand_total"] == 465
	cwb = g["footer"][0]
	assert cwb["qty"] == 25 and cwb["po_refs"] == ["IFPO1", "IFPO2"]
	assert cwb["amount"] == 150 and not cwb["invoiced"] and cwb["invoice_count"] == 0


def test_grid_invoices():
	inv = [{"name": "INV-1", "sales_order": "SO-1", "grand_total": 105},
	       {"name": "INV-2", "sales_order": "SO-2", "grand_total": 52.5},
	       {"name": "INV-2", "sales_order": "SO-2", "grand_total": 52.5}]
	g = build_grid(DAY, _lines(), CUSTOMERS, ITEMS, inv)
	cwb = g["footer"][0]
	assert cwb["invoices"] == ["INV-1", "INV-2"] and cwb["invoice_count"] == 2
	assert cwb["amount"] == 157.5 and cwb["invoiced"]


def test_group_spans_split_when_not_adjacent():
	cols = [{"group": "A"}, {"group": "B"}, {"group": "A"}]
	assert group_spans(cols) == [("A", 1), ("B", 1), ("A", 1)]


def test_placeholder_items_fold_into_customer_code_and_drafts_flagged():
	lines = [
		{"sales_order": "SO-1", "customer": "AMEX", "item_code": "SKU-0017", "customer_item_code": "1031001053",
		 "item_name": "Tropical", "qty": 400, "uom": "Nos", "docstatus": 0},
		{"sales_order": "SO-2", "customer": "AMEX", "item_code": "1031001053", "item_name": "Tropical", "qty": 100,
		 "uom": "Nos", "docstatus": 1},
		{"sales_order": "SO-3", "customer": "K11", "item_code": "1031001053", "item_name": "Tropical", "qty": 5,
		 "uom": "Nos", "docstatus": 1},
	]
	g = build_grid(DAY, lines, CUSTOMERS, {})
	assert len(g["rows"]) == 1
	r = g["rows"][0]
	assert r["item_code"] == "1031001053" and r["total"] == 505
	assert r["qtys"] == [5, 500]
	assert r["drafts"] == [False, True]
