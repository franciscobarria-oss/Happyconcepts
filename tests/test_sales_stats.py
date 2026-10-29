import json
from datetime import date

from happy_kitchen.hk_operations import sales_stats as s
from happy_kitchen.setup.workspace_content import with_block_on_top


def ln(d, item, qty, order, amount=0, uom="Nos"):
	return {"date": d, "item_code": item, "item_name": item.title(), "uom": uom, "qty": qty, "amount": amount, "order": order}


LINES = [
	ln("2026-09-28", "bun", 10, "SO1", 50),   # Mon, week of 28 Sep
	ln("2026-09-28", "cake", 2, "SO1", 80),
	ln("2026-10-03", "bun", 5, "SO2", 25),    # Sat
	ln("2026-10-06", "bun", 20, "SO3", 100),  # Tue, week of 5 Oct
	ln("2026-10-20", "cake", 4, "SO4", 160),  # Tue, week of 19 Oct
	ln("2026-10-20", "bun", 6, "SO4", 30),
]


def test_week_start_is_monday():
	assert s.week_start(date(2026, 10, 25)) == date(2026, 10, 19)  # Sunday
	assert s.week_start(date(2026, 10, 19)) == date(2026, 10, 19)


def test_skus_sold_most_units_first_with_orders_and_share():
	rows = s.skus_sold(LINES)
	assert [r["item_code"] for r in rows] == ["bun", "cake"]
	bun = rows[0]
	assert bun["qty"] == 41 and bun["amount"] == 205 and bun["orders"] == 4
	assert round(bun["share"], 4) == round(41 / 47, 4)


def test_same_item_in_two_units_stays_apart():
	rows = s.skus_sold([ln("2026-10-01", "flour", 2, "A", uom="Kg"), ln("2026-10-01", "flour", 3, "B", uom="Bag")])
	assert {(r["uom"], r["qty"]) for r in rows} == {("Kg", 2), ("Bag", 3)}


def test_weekly_fills_empty_weeks():
	weeks = s.weekly(LINES, "2026-09-28", "2026-10-25")
	assert [w["week"] for w in weeks] == ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]
	assert [w["qty"] for w in weeks] == [17, 20, 0, 10]
	assert [w["orders"] for w in weeks] == [2, 1, 0, 1]


def test_recent_weekdays_ends_with_last_delivery_week():
	r = s.recent_weekdays(LINES, "2026-10-31")
	assert r["from"] == "2026-09-28" and r["to"] == "2026-10-25"
	assert [w["week"] for w in r["weeks"]] == ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]
	assert r["weeks"][0]["days"] == [12, 0, 0, 0, 0, 5, 0]
	assert r["totals"] == [12, 30, 0, 0, 0, 5, 0]
	assert r["average"][1] == 7.5
	assert r["busiest_weekday"] == "Tue"
	assert r["busiest_date"] == {"date": "2026-10-06", "qty": 20}


def test_recent_weekdays_ignores_deliveries_after_range_end():
	r = s.recent_weekdays(LINES, "2026-10-10")
	assert r["to"] == "2026-10-11"  # last delivery on or before 10 Oct is 6 Oct
	assert sum(r["totals"]) == 37


def test_recent_weekdays_empty():
	assert s.recent_weekdays([], "2026-10-10") is None


def test_summarise_keeps_only_the_range():
	out = s.summarise(LINES, "2026-10-01", "2026-10-31")
	assert out["totals"] == {"qty": 35, "amount": 315, "orders": 3, "skus": 2}
	assert out["weeks"][0]["week"] == "2026-09-28" and out["weeks"][0]["qty"] == 5
	assert out["recent"]["busiest_weekday"] == "Tue"


def test_block_goes_on_top_once_and_onboarding_goes():
	content = json.dumps([
		{"id": "a", "type": "onboarding", "data": {"onboarding_name": "Selling Onboarding"}},
		{"id": "b", "type": "chart", "data": {"chart_name": "Sales Order Analysis"}},
	])
	once = with_block_on_top(content, "HK Sales", "hk-sales")
	blocks = json.loads(once)
	assert [b["type"] for b in blocks] == ["custom_block", "chart"]
	assert blocks[0]["data"] == {"custom_block_name": "HK Sales", "col": 12}
	assert with_block_on_top(once, "HK Sales", "hk-sales") == once
