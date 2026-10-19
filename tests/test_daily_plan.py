import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.recipe_management import daily_plan as dp  # noqa: E402
from happy_kitchen.recipe_management.variance import VarianceError  # noqa: E402

FP, BP, RC = "Finished Product", "Batch Preparation", "Recipe Component"

# Cookie made from dough (batch prep, 200 balls per batch); dough from flour + butter.
# Cake with a fresh cream component; cream from cream + sugar.
RECIPE_FOR_ITEM = {
	"COOKIE": {"recipe": "COOKIE", "recipe_type": FP, "batch_yield": 100},
	"DOUGH": {"recipe": "DOUGH", "recipe_type": BP, "batch_yield": 200},
	"CAKE": {"recipe": "CAKE", "recipe_type": FP, "batch_yield": 1},
	"CREAM": {"recipe": "CREAM", "recipe_type": RC, "batch_yield": 1000},  # grams
}
SUB = {k: v for k, v in RECIPE_FOR_ITEM.items() if v["recipe_type"] in (BP, RC)}
LINES = {
	"COOKIE": [{"item": "DOUGH", "gross_qty": 100}, {"item": "SUGAR", "gross_qty": 50}],  # per 100 cookies
	"DOUGH": [{"item": "FLOUR", "gross_qty": 5000}, {"item": "BUTTER", "gross_qty": 2000}],  # per 200 balls
	"CAKE": [{"item": "CREAM", "gross_qty": 250}, {"item": "FLOUR", "gross_qty": 300}],
	"CREAM": [{"item": "CREAM_RAW", "gross_qty": 900}, {"item": "SUGAR", "gross_qty": 100}],  # per 1000 g
}


def plan(demand, stock=None, **kw):
	return dp.plan_day(demand, RECIPE_FOR_ITEM, SUB, LINES, stock or {}, **kw)


def by_item(rows):
	return {r["item"]: r for r in rows}


def test_whole_batches():
	assert dp.whole_batches(0, 100) == 0
	assert dp.whole_batches(1, 100) == 1
	assert dp.whole_batches(100, 100) == 1
	assert dp.whole_batches(100.0000001, 100) == 1  # float noise doesn't add a batch
	assert dp.whole_batches(101, 100) == 2
	assert dp.whole_batches(3, 0) == 3  # no yield -> per unit


def test_rounds_up_to_batches_and_uses_finished_stock():
	p = plan({"COOKIE": 250}, stock={"COOKIE": 30})
	m = p["make"][0]
	assert (m["to_make"], m["batches"], m["units"]) == (220, 3, 300)


def test_ignore_finished_stock():
	m = plan({"COOKIE": 250}, stock={"COOKIE": 30}, use_finished_stock=False)["make"][0]
	assert (m["to_make"], m["batches"]) == (250, 3)


def test_enough_finished_stock_makes_nothing():
	p = plan({"COOKIE": 80}, stock={"COOKIE": 100, "DOUGH": 0})
	assert p["make"][0]["batches"] == 0
	assert p["preps"] == [] and p["ingredients"] == []


def test_dough_from_stock_then_suggest_more():
	# 3 cookie batches need 300 dough balls; 120 in the freezer -> short 180 -> 1 dough batch (200)
	p = plan({"COOKIE": 300}, stock={"DOUGH": 120, "FLOUR": 1000, "BUTTER": 5000, "SUGAR": 10000})
	d = by_item(p["preps"])["DOUGH"]
	assert (d["need"], d["in_stock"], d["short"], d["batches"], d["units"]) == (300, 120, 180, 1, 200)
	ing = by_item(p["ingredients"])
	assert ing["FLOUR"]["need"] == 5000 and ing["FLOUR"]["short"] == 4000
	assert ing["BUTTER"]["short"] == 0
	assert ing["SUGAR"]["need"] == 150
	assert p["ingredients"][0]["item"] == "FLOUR"  # shortages first


def test_enough_dough_no_suggestion_and_no_dough_ingredients():
	p = plan({"COOKIE": 100}, stock={"DOUGH": 500})
	assert by_item(p["preps"])["DOUGH"]["batches"] == 0
	assert "FLOUR" not in by_item(p["ingredients"])


def test_component_expanded_fresh():
	p = plan({"CAKE": 4})
	assert p["components"] == [{"recipe": "CREAM", "units": 1000}]
	ing = by_item(p["ingredients"])
	assert ing["CREAM_RAW"]["need"] == pytest.approx(900)
	assert ing["SUGAR"]["need"] == pytest.approx(100)
	assert ing["FLOUR"]["need"] == 1200


def test_dough_sold_as_is_and_bought_in_item():
	p = plan({"DOUGH": 400, "WATER": 10}, stock={"DOUGH": 100, "WATER": 4})
	assert by_item(p["preps"])["DOUGH"]["batches"] == 2  # short 300 -> 2 x 200
	assert p["pick"] == [{"item": "WATER", "need": 10, "in_stock": 4, "short": 6}]


def test_negative_stock_counts_as_zero():
	d = by_item(plan({"COOKIE": 100}, stock={"DOUGH": -50})["preps"])["DOUGH"]
	assert d["short"] == 100 and d["batches"] == 1


def test_prep_inside_prep():
	rfi = dict(RECIPE_FOR_ITEM, BASE={"recipe": "BASE", "recipe_type": BP, "batch_yield": 10})
	sub = {k: v for k, v in rfi.items() if v["recipe_type"] in (BP, RC)}
	lines = dict(LINES, DOUGH=[{"item": "BASE", "gross_qty": 4}, {"item": "FLOUR", "gross_qty": 10}],
	             BASE=[{"item": "EGG", "gross_qty": 12}])
	p = dp.plan_day({"COOKIE": 200}, rfi, sub, lines, {})
	preps = by_item(p["preps"])
	assert preps["DOUGH"]["batches"] == 1  # 200 balls
	assert preps["BASE"]["need"] == 4 and preps["BASE"]["batches"] == 1
	assert by_item(p["ingredients"])["EGG"]["need"] == 12


def test_recipe_loop_is_reported():
	# component A uses component B, which uses A again
	rfi = dict(RECIPE_FOR_ITEM, A={"recipe": "A", "recipe_type": RC, "batch_yield": 1},
	           B={"recipe": "B", "recipe_type": RC, "batch_yield": 1},
	           TOP={"recipe": "TOP", "recipe_type": FP, "batch_yield": 1})
	sub = {k: v for k, v in rfi.items() if v["recipe_type"] in (BP, RC)}
	lines = dict(LINES, TOP=[{"item": "A", "gross_qty": 1}], A=[{"item": "B", "gross_qty": 1}], B=[{"item": "A", "gross_qty": 1}])
	with pytest.raises(VarianceError):
		dp.plan_day({"TOP": 1}, rfi, sub, lines, {})
