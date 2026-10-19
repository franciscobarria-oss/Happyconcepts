import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.recipe_management import board  # noqa: E402


def test_order_qty_minimum_and_multiple():
	assert board.order_qty(0) == 0
	assert board.order_qty(-5) == 0
	assert board.order_qty(300) == 300
	assert board.order_qty(300, min_qty=1000) == 1000
	assert board.order_qty(13, multiple=12) == 24  # eggs by the dozen
	assert board.order_qty(24, multiple=12) == 24
	assert board.order_qty(5, min_qty=30, multiple=12) == 36


ITEMS = {
	"FLOUR": {"item_name": "Cake Flour", "stock_uom": "Gram", "supplier": "S1", "supplier_name": "Tak Shing", "min_order_qty": 22700},
	"EGG": {"item_name": "Eggs", "stock_uom": "Nos", "supplier": "S2", "supplier_name": "Egg Co", "order_multiple": 12},
	"SALT": {"item_name": "Salt", "stock_uom": "Gram", "supplier": "S1", "supplier_name": "Tak Shing"},
	"MYSTERY": {"item_name": "Mystery", "stock_uom": "Gram"},
}


def test_to_order_groups_by_supplier_and_subtracts_what_is_on_order():
	short = [
		{"item": "FLOUR", "short": 5000, "need_by": "2026-10-16"},
		{"item": "EGG", "short": 30, "need_by": "2026-10-15"},
		{"item": "SALT", "short": 200, "need_by": "2026-10-15"},
		{"item": "MYSTERY", "short": 10, "need_by": "2026-10-15"},
	]
	groups = board.to_order(short, {"SALT": 50}, ITEMS)
	assert [g["supplier"] for g in groups] == ["S2", "S1", ""]  # both needed today, so by name; no supplier last
	s1 = groups[1]
	assert s1["need_by"] == "2026-10-15"
	assert [l["item"] for l in s1["lines"]] == ["SALT", "FLOUR"]  # most urgent first
	salt, flour = s1["lines"]
	assert salt["short"] == 150 and salt["on_order"] == 50 and salt["qty"] == 150
	assert flour["qty"] == 22700  # a whole bag
	assert groups[0]["lines"][0]["qty"] == 36  # 30 eggs -> 3 dozen


def test_fully_ordered_items_drop_out():
	short = [{"item": "SALT", "short": 200, "need_by": "2026-10-15"}]
	assert board.to_order(short, {"SALT": 200}, ITEMS) == []
	assert board.to_order(short, {"SALT": 500}, ITEMS) == []


def test_first_need_uses_cumulative_plans():
	plans = [
		("2026-10-15", {"ingredients": [{"item": "A", "short": 0}, {"item": "B", "short": 5}]}),
		("2026-10-16", {"ingredients": [{"item": "A", "short": 10}, {"item": "B", "short": 8}]}),
		("2026-10-17", {"ingredients": [{"item": "A", "short": 25}, {"item": "B", "short": 8}]}),
	]
	got = board.first_need(plans)
	assert got == [
		{"item": "B", "need_by": "2026-10-15", "short": 8},
		{"item": "A", "need_by": "2026-10-16", "short": 25},
	]


def test_production_progress():
	make = [
		{"item": "C1", "recipe": "R1", "batches": 2, "units": 200},
		{"item": "C2", "recipe": "R2", "batches": 1, "units": 1000},
		{"item": "C3", "recipe": "R3", "batches": 0, "units": 0},  # covered by stock, nothing logged
	]
	rows = board.production_progress(make, {"R1": 200, "R2": 400})
	assert [r["recipe"] for r in rows] == ["R2", "R1"]  # unfinished first
	r2, r1 = rows
	assert r1["done"] and r1["left"] == 0
	assert not r2["done"] and r2["left"] == pytest.approx(600)
	# something made that wasn't planned still shows
	extra = board.production_progress([{"item": "C3", "recipe": "R3", "batches": 0, "units": 0}], {"R3": 50})
	assert extra[0]["made"] == 50 and not extra[0]["done"]


def test_merge_today_adds_breakdowns_and_extra_tiles():
	dash = {
		"today": "2026-10-19",
		"kpis": [
			{"key": "orders", "label": "Orders to deliver", "value": "5", "details": [{"label": "Cafe A", "value": "HK$ 100"}]},
			{"key": "produced", "label": "Produced today", "value": "3", "unit": "batches", "details": [{"label": "Dough", "value": "3 batches"}]},
			{"key": "open_po", "label": "Open purchase orders", "value": "HK$ 900", "delta": "2 orders to receive", "route": "List/Purchase Order"},
			{"key": "waste", "label": "Waste this week", "value": "HK$ 50", "unit": "", "details": []},
		],
		"orders": [{"key": "today", "count": 1}],
		"orders_total": 1,
		"waiting": [
			{"label": "Purchase orders to send", "route": "List/Purchase Order?docstatus=0"},
			{"label": "Check delivery from Egg Co", "route": "Form/Purchase Receipt/PR-1"},
		],
	}
	brd = {
		"today": "2026-10-19",
		"tiles": [{"key": "orders", "label": "Orders going out", "value": 2}, {"key": "production", "label": "To make today", "value": "4"}],
		"now": {"orders": []},
		"tasks": {
			"ordering": {"groups": [], "drafts": 1},
			"receiving": [{"label": "Receive Egg Co", "route": "receive-delivery/PO-1"}, {"label": "Check delivery", "route": "Form/Purchase Receipt/PR-1"}],
			"production": [],
		},
	}
	out = board.merge_today(dash, brd)
	assert [t["key"] for t in out["tiles"]] == ["orders", "production", "open_po", "waste"]
	assert out["tiles"][0]["details"] == [{"label": "Cafe A", "value": "HK$ 100"}]
	assert out["tiles"][1]["details"][0]["label"] == "Dough"
	assert out["tiles"][2]["detail"] == "2 orders to receive"
	assert out["tiles"][3]["value"] == "HK$ 50"
	# flagged deliveries and draft POs stay under "Waiting on you" only
	assert [t["route"] for t in out["tasks"]["receiving"]] == ["receive-delivery/PO-1"]
	assert out["tasks"]["ordering"]["drafts"] == 0
	assert out["orders_total"] == 1 and out["today"] == "2026-10-19"


def test_merge_today_without_board_tiles_skips_duplicates():
	dash = {"kpis": [{"key": "deliveries", "label": "Deliveries due", "value": "1"}], "waiting": []}
	out = board.merge_today(dash, {"tiles": [], "tasks": {"ordering": None, "receiving": None, "production": None}})
	assert out["tiles"] == []
	assert out["tasks"]["receiving"] is None
