import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.recipe_management.swap import new_qty, plan_swap  # noqa: E402

LINES = [
	{"item": "FLOUR", "qty": 500, "uom": "g", "yield_pct": 100},
	{"item": "BUTTER-A", "qty": 200, "uom": "g", "yield_pct": 100},
	{"item": "SUGAR", "qty": 150, "uom": "g", "yield_pct": 100},
	{"item": "BUTTER-A", "qty": 20, "uom": "g", "yield_pct": 100},  # a second line (e.g. for greasing)
]


def test_replaces_every_line_of_the_old_ingredient():
	assert plan_swap(LINES, "BUTTER-A", "BUTTER-B") == [("replace", 1, 200), ("replace", 3, 20)]


def test_factor_scales_the_quantity():
	assert plan_swap(LINES, "BUTTER-A", "BUTTER-B", 0.8) == [("replace", 1, 160), ("replace", 3, 16)]
	assert new_qty(0.1, 3) == 0.3  # no float noise


def test_merges_into_a_line_that_already_uses_the_new_item():
	lines = LINES + [{"item": "BUTTER-B", "qty": 50, "uom": "g", "yield_pct": None}]
	assert plan_swap(lines, "BUTTER-A", "BUTTER-B") == [("merge", 1, 4, 200), ("merge", 3, 4, 20)]
	# a different unit stays a separate line
	lines = LINES + [{"item": "BUTTER-B", "qty": 1, "uom": "kg", "yield_pct": 100}]
	assert plan_swap(lines, "BUTTER-A", "BUTTER-B")[0] == ("replace", 1, 200)


def test_nothing_to_do():
	assert plan_swap(LINES, "BUTTER-A", "BUTTER-A") == []
	assert plan_swap(LINES, "EGG", "BUTTER-B") == []
	assert plan_swap(LINES, "BUTTER-A", "") == []
