from happy_kitchen.hk_operations import sku


def test_search_text_lists_each_supplier_sku_once():
	rows = [{"supplier": "A", "supplier_part_no": " X-1 "}, {"supplier": "B", "supplier_part_no": "X-1"},
	        {"supplier": "C", "supplier_part_no": "Y2"}, {"supplier": "D", "supplier_part_no": None}]
	assert sku.search_text(rows) == "X-1, Y2"
	assert sku.search_text([]) == ""


def test_repeated_sku_for_one_supplier():
	rows = [{"supplier": "A", "supplier_part_no": "x-1"}, {"supplier": "B", "supplier_part_no": "x-1"}]
	assert sku.repeated_in_item(rows) is None  # two suppliers may share a code
	rows.append({"supplier": "A", "supplier_part_no": "X-1"})
	assert sku.repeated_in_item(rows) == ("A", "X-1")


def test_sku_for_supplier():
	rows = [{"supplier": "A", "supplier_part_no": "x"}, {"supplier": "B", "supplier_part_no": " y "}]
	assert sku.sku_for_supplier(rows, "B") == "y"
	assert sku.sku_for_supplier(rows, "C") == ""
