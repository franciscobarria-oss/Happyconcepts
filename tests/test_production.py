import pytest

from happy_kitchen.recipe_management import production as p


def test_whole_units_round_up():
	assert p.stock_qty(0.025, True) == 1
	assert p.stock_qty(2.0, True) == 2
	assert p.stock_qty(2.0000000001, True) == 2  # float noise is not a whole extra egg
	assert p.stock_qty(2.01, True) == 3


def test_weights_keep_three_decimals():
	assert p.stock_qty(12.34567, False) == 12.346
	assert p.stock_qty(None, False) == 0


def test_clean_entries_drops_empty_and_merges():
	got = p.clean_entries('[{"recipe": "DOUGH", "batches": 1}, {"recipe": "", "batches": 2},'
	                      ' {"recipe": "COOKIE", "batches": 0}, {"recipe": "DOUGH", "batches": 0.5}]')
	assert got == [{"recipe": "DOUGH", "batches": 1.5}]


def test_clean_entries_needs_something():
	with pytest.raises(ValueError):
		p.clean_entries([{"recipe": "X", "batches": 0}])


def test_preview_puts_short_items_first():
	rows = [
		{"item": "B", "item_name": "Butter", "gross_qty": 100, "actual_qty": 500, "shortage_qty": 0, "estimated_cost": 5},
		{"item": "E", "item_name": "egg", "gross_qty": 3, "actual_qty": 1, "shortage_qty": 2, "estimated_cost": 4.5},
		{"item": "A", "item_name": "Almond", "gross_qty": 10, "actual_qty": 10, "shortage_qty": 0, "estimated_cost": 1},
	]
	out = p.preview(rows)
	assert [l["item"] for l in out["lines"]] == ["E", "A", "B"]
	assert out["short_count"] == 1
	assert out["total_cost"] == pytest.approx(10.5)


def test_split_runs():
	rows = [{"recipe": "DOUGH"}, {"recipe": "COOKIE"}, {"recipe": "SAUCE"}]
	batch, other = p.split_runs(rows, {"DOUGH": "Batch Preparation", "COOKIE": "Finished Product",
	                                   "SAUCE": "Recipe Component"})
	assert batch == [{"recipe": "DOUGH"}]
	assert other == [{"recipe": "COOKIE"}, {"recipe": "SAUCE"}]
