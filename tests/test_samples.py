from happy_kitchen.hk_operations.samples import add_to_demand, box_rows


def test_samples_add_to_demand_without_changing_input():
	demand = {"A": 10.0}
	out = add_to_demand(demand, [{"item": "A", "stock_qty": 2}, {"item": "B", "stock_qty": 3}, {"item": "C", "stock_qty": 0}])
	assert out == {"A": 12.0, "B": 3.0} and demand == {"A": 10.0}


def test_box_rows_group_by_item_and_name_recipients_once():
	rows = box_rows([
		{"item": "B", "item_name": "Beta", "qty": 2, "uom": "Nos", "recipient": "Hotel X"},
		{"item": "A", "item_name": "Alpha", "item_name_zh": "甲", "qty": 1, "uom": "Nos", "customer_name": "K11"},
		{"item": "A", "item_name": "Alpha", "qty": 4, "uom": "Nos", "customer_name": "K11"},
		{"item": "A", "item_name": "Alpha", "qty": 1, "uom": "Nos", "recipient": "Hotel X", "customer_name": "K11"},
		{"item": "Z", "qty": 0, "uom": "Nos", "recipient": "Nobody"},
	])
	assert [r["item"] for r in rows] == ["A", "B"]
	assert rows[0]["qty"] == 6 and rows[0]["to"] == "K11, Hotel X" and rows[0]["item_name_zh"] == "甲"
