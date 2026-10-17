import pytest

from happy_kitchen.hk_operations import moq


def test_total_stock_qty_sums_lines():
	lines = [
		{"item_code": "ING-057", "stock_qty": 12},
		{"item_code": "ING-057", "qty": 2, "conversion_factor": 6},
		{"item_code": "ING-001", "qty": 500},
		{"item_code": None, "qty": 3},
	]
	assert moq.total_stock_qty(lines) == {"ING-057": 24.0, "ING-001": 500.0}


@pytest.mark.parametrize("qty,mult,expected", [
	(24, 12, None), (12, 0, None), (5, None, None), (13, 12, (12, 24)), (5, 12, (None, 12)),
	(0.3, 0.1, None),  # float noise is not an error
])
def test_multiple_suggestion(qty, mult, expected):
	assert moq.multiple_suggestion(qty, mult) == expected


def test_multiple_errors():
	items = {"ING-057": {"item_name": "Egg", "stock_uom": "Nos", "hk_order_multiple": 12},
	         "ING-001": {"item_name": "Flour", "stock_uom": "Gram", "hk_order_multiple": 0}}
	errs = moq.multiple_errors({"ING-057": 30, "ING-001": 7}, items)
	assert errs == [{"item_code": "ING-057", "item_name": "Egg", "stock_uom": "Nos", "qty": 30,
	                 "multiple": 12.0, "lower": 24, "upper": 36}]


@pytest.mark.parametrize("total,minimum,gap", [(300, 500, 200), (500, 500, 0), (600, 500, 0), (100, 0, 0), (100, None, 0)])
def test_minimum_shortfall(total, minimum, gap):
	assert moq.minimum_shortfall(total, minimum) == gap


def test_next_item_code():
	assert moq.next_item_code([]) == "ING-001"
	assert moq.next_item_code(["ING-001", "ING-167", "ING-020", "RJ0018", "ING-X"]) == "ING-168"
	assert moq.next_item_code(["ING-999"]) == "ING-1000"


def test_to_stock_units():
	assert moq.to_stock_units(80, "Kg", (2, 0.5)) == ("Gram", 0.08, [2000, 500])
	assert moq.to_stock_units(3.5, "Nos", (12,)) == ("Nos", 3.5, [12])
	with pytest.raises(ValueError):
		moq.to_stock_units(1, "lb")
