import pytest

from happy_kitchen.recipe_management import costing as c


def test_to_base_qty_converts_units():
	assert c.to_base_qty(2, "kg") == 2000
	assert c.to_base_qty(1, "lb") == pytest.approx(453.592)
	assert c.to_base_qty(250, "ml") == 250
	assert c.to_base_qty(3, "piece") == 3
	with pytest.raises(c.CostingError):
		c.to_base_qty(1, "cup")


def test_uom_must_match_stock_uom():
	c.check_uom_compatible("kg", "Gram")
	c.check_uom_compatible("piece", "Nos")
	with pytest.raises(c.CostingError):
		c.check_uom_compatible("piece", "Gram")
	with pytest.raises(c.CostingError):
		c.check_uom_compatible("g", "Nos")
	c.check_uom_compatible("g", "Box")  # unknown stock UOM is not blocked


def test_gross_qty_applies_yield():
	assert c.gross_qty(80, 80) == pytest.approx(100)
	assert c.gross_qty(50, None) == 50  # blank yield = 100%
	for bad in (0, -5, 120):
		with pytest.raises(c.CostingError):
			c.gross_qty(10, bad)


def test_price_per_base_unit_uses_conversion():
	assert c.price_per_base_unit(120, 1000) == pytest.approx(0.12)  # $120/kg -> $/g
	assert c.price_per_base_unit(5, 0) == 5  # bad factor falls back to 1


def test_pick_price_cheapest_and_supplier():
	prices = [
		{"supplier": "A", "price_per_base_unit": 0.02},
		{"supplier": "B", "price_per_base_unit": 0.015},
		{"supplier": "C", "price_per_base_unit": 0},
	]
	assert c.pick_price(prices)["supplier"] == "B"  # zero price ignored
	assert c.pick_price(prices, "A")["supplier"] == "A"
	assert c.pick_price(prices, "Z") is None
	assert c.pick_price([{"supplier": "C", "price_per_base_unit": 0}])["supplier"] == "C"
	assert c.pick_price([]) is None


def test_cost_line_charges_gross():
	line = c.cost_line(0.5, "kg", 50, 0.01)
	assert line["base_qty"] == 500
	assert line["gross_qty"] == 1000
	assert line["line_cost"] == pytest.approx(10)


def test_summarize_with_labour_overheads_and_price():
	s = c.summarize(
		ingredient_costs=[6.0, 4.0],
		labour=[{"hourly_rate": 60, "minutes": 30}, {"hourly_rate": 80, "minutes": 15}],
		overheads=[
			{"basis": "Per Batch", "rate": 5},
			{"basis": "Per Unit", "rate": 0.5},
			{"basis": "% of Ingredient Cost", "rate": 10},
			{"basis": "% of Labour Cost", "rate": 20},
			{"basis": "Per Labour Hour", "rate": 8},
		],
		batch_yield=10,
		selling_price=10,
		target_food_cost_pct=25,
	)
	assert s["total_ingredient_cost"] == 10
	assert s["labour_costs"] == [30, 20]
	assert s["total_labour_cost"] == 50
	assert s["total_labour_minutes"] == 45
	assert s["overhead_amounts"] == pytest.approx([5, 5, 1, 10, 6])
	assert s["total_overhead_cost"] == pytest.approx(27)
	assert s["total_batch_cost"] == pytest.approx(87)
	assert s["cost_per_unit"] == pytest.approx(8.7)
	assert s["ingredient_cost_per_unit"] == 1
	assert s["cost_shares"] == pytest.approx([60, 40])
	assert s["food_cost_pct"] == pytest.approx(10)
	assert s["total_cost_pct"] == pytest.approx(87)
	assert s["gross_margin"] == pytest.approx(1.3)
	assert s["suggested_price"] == pytest.approx(4)


def test_summarize_rejects_zero_yield_and_unknown_basis():
	with pytest.raises(c.CostingError):
		c.summarize(ingredient_costs=[1], labour=[], overheads=[], batch_yield=0)
	with pytest.raises(c.CostingError):
		c.summarize(ingredient_costs=[1], labour=[], overheads=[{"basis": "Weekly", "rate": 1}], batch_yield=1)


def test_summarize_without_price_leaves_ratios_zero():
	s = c.summarize(ingredient_costs=[], labour=[], overheads=[], batch_yield=1)
	assert s["food_cost_pct"] == 0 and s["suggested_price"] == 0 and s["cost_shares"] == []


def test_allocate_loaded_costs():
	assert c.allocate_loaded_costs([3, 1], 6, 2) == pytest.approx([9, 3])
	assert c.allocate_loaded_costs([0, 0], 4, 0) == [2, 2]
	assert c.allocate_loaded_costs([], 4, 0) == []


def test_cooking_yield():
	assert c.cooking_yield(1000, 10, 85) == (850, pytest.approx(85))
	assert c.cooking_yield(0, 10, 85) == (850, 0.0)
	assert c.cooking_yield(1000, 10, None) == (0, 0.0)


def test_aggregate_usage_sums_across_recipes():
	lines = {
		"FC0008": [
			{"item": "ING-002", "item_name": "Butter", "stock_uom": "Gram", "base_qty": 100, "gross_qty": 100, "price_per_base_unit": 0.1, "supplier": "A"},
			{"item": "ING-001", "item_name": "Egg", "stock_uom": "Nos", "base_qty": 2, "gross_qty": 2, "price_per_base_unit": 1.5, "supplier": "B"},
		],
		"IK0008": [
			{"item": "ING-002", "item_name": "Butter", "stock_uom": "Gram", "base_qty": 40, "gross_qty": 50, "price_per_base_unit": 0.1, "supplier": "A"},
		],
	}
	runs = [{"recipe": "FC0008", "batches": 2}, {"recipe": "IK0008", "batches": 3}, {"recipe": "IK0008", "batches": 0}]
	rows = c.aggregate_usage(runs, lines)
	assert [r["item"] for r in rows] == ["ING-001", "ING-002"]
	egg, butter = rows
	assert egg["gross_qty"] == 4 and egg["estimated_cost"] == pytest.approx(6)
	assert butter["net_qty"] == 320
	assert butter["gross_qty"] == 350
	assert butter["waste_qty"] == 30
	assert butter["estimated_cost"] == pytest.approx(35)
	assert butter["recipes"] == ["FC0008", "IK0008"]


def test_weight_per_piece_conversions():
	# egg stocked in pieces, 56.2 g each, recipe in grams
	assert c.to_stock_qty(112.4, "g", "Nos", 56.2) == pytest.approx(2)
	# tea bag stocked in grams, 2 g each, recipe in pieces
	assert c.to_stock_qty(4, "piece", "Gram", 2) == 8
	with pytest.raises(c.CostingError):
		c.to_stock_qty(100, "g", "Nos", None)
	assert c.to_stock_qty(1, "kg", "Gram") == 1000
	line = c.cost_line(231, "g", 100, 0.833333, "Nos", 56.2)
	assert line["base_qty"] == pytest.approx(4.1103, abs=1e-4)
	assert line["line_cost"] == pytest.approx(3.4253, abs=1e-3)
	assert c.line_grams(2, "piece", 56.2) == pytest.approx(112.4)
	assert c.line_grams(2, "piece", None) == 0
	assert c.grams_per_piece(0.2, "Kg") == 200
	assert c.grams_per_piece(56.2, None) == 56.2
