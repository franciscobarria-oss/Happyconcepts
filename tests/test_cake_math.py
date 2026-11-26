import math

from happy_kitchen.recipe_management import cake_math as c


def test_volume_shapes():
	assert math.isclose(c.volume_cm3("Round", 9, 18), math.pi * 81 * 9)
	assert c.volume_cm3("Square", 5, 20) == 2000
	assert c.volume_cm3("Loaf", 5, 10, 20) == 1000
	assert c.volume_cm3("Round", 0, 18) == 0


def test_slices():
	assert c.suggest_slices(1150) == 12
	assert c.suggest_slices(20) == 1
	assert c.suggest_slices(0) == 0


def test_totals_skip_unpriced():
	t = c.totals([{"qty_g": 100, "unit_cost": 0.1}, {"qty_g": 50, "unit_cost": None, "item_name": "Cream"}],
	             labour=2, packaging=1, slices=4, weight_g=500)
	assert t["ingredient_cost"] == 10 and t["total_cost"] == 13
	assert t["cost_per_slice"] == 3.25 and t["cost_per_100g"] == 2.6
	assert t["unpriced"] == ["Cream"]


def test_precision_kept():
	assert c.line_cost(0.025, 0.0123) == round(0.025 * 0.0123, 4)


def test_parse_guess_drops_bad_rows():
	d = {"ingredients": [{"name": " Butter ", "grams": 250}, {"name": "", "grams": 5}, {"name": "x", "grams": 0}, {"name": "Egg", "grams": "abc"}]}
	assert c.parse_guess(d) == [{"name": "Butter", "grams": 250.0}]
	assert c.parse_guess(None) == []


def test_weight_gap():
	assert c.ingredient_weight_gap([{"qty_g": 1200}], 1000) == 20.0
	assert c.ingredient_weight_gap([], 0) is None


def test_pack_cost_weight_units():
	r = c.pack_cost(475, 13.6, "kg", 100, "g")
	assert math.isclose(r["unit_cost"], 475 / 13600) and math.isclose(r["line_cost"], round(100 * 475 / 13600, 4)) and r["weight_g"] == 100
	assert math.isclose(c.pack_cost(330, 24, "lb", 34)["unit_cost"], 330 / (24 * 453.592))


def test_pack_cost_pieces():
	r = c.pack_cost(300, 360, "pcs", 4, "pcs", 48.75)
	assert math.isclose(r["line_cost"], round(4 * 300 / 360, 4)) and r["weight_g"] == 195


def test_pack_cost_errors():
	assert "error" in c.pack_cost(6, 1, "pcs", 1, "g")
	assert c.pack_cost(5, 0, "kg", 10)["error"] == "No pack size"


def test_per_piece():
	assert c.per_piece(100, 800, 80) == (10.0, 10.0)
	assert c.per_piece(100, 800, 0, slices=4) == (4.0, 25.0)
	assert c.per_piece(100, 0, 0) == (0.0, 0.0)
