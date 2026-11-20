from datetime import date, datetime

from happy_kitchen.hk_operations import pay_sheet as p


def test_month_bounds():
	assert p.month_bounds("2026-10") == (date(2026, 10, 1), date(2026, 10, 31))
	assert p.month_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
	assert p.month_bounds("2026-02")[1] == date(2026, 2, 28)


def test_worked_hours_only_counts_month():
	c = [("IN", datetime(2026, 9, 30, 8)), ("OUT", datetime(2026, 9, 30, 12)),
	     ("IN", datetime(2026, 10, 1, 8)), ("OUT", datetime(2026, 10, 1, 12, 30)),
	     ("IN", datetime(2026, 10, 31, 9))]
	assert p.worked_hours(c, date(2026, 10, 1), date(2026, 10, 31)) == 4.5


def test_hourly_row():
	r = p.pay_row(p.HOURLY, hourly_rate=60, hours=10.5, ot_hours=2, ot_amount=180)
	assert r["basic"] == 630 and r["total"] == 810 and r["rate"] == 60


def test_monthly_row_ignores_hours():
	r = p.pay_row(p.MONTHLY, monthly_base=18000, hours=170, ot_amount=0)
	assert r["basic"] == 18000 and r["total"] == 18000


def test_contract_type_fallback():
	assert p.contract_type(None, 15000, 0) == p.MONTHLY
	assert p.contract_type("", 0, 55) == p.HOURLY
	assert p.contract_type(p.HOURLY, 15000, 0) == p.HOURLY


def test_problems():
	r = p.pay_row(p.HOURLY, hourly_rate=0, hours=0)
	assert p.problems(r) == ["No rate set", "No hours", "No bank account"]
	assert p.problems({**p.pay_row(p.MONTHLY, 100), "bank_ac_no": "x"}) == []


def test_mpf_normal_month():
	m = p.mpf(20000)
	assert m["mpf_employee"] == 1000 and m["mpf_employer"] == 1000 and m["mpf_note"] == ""


def test_mpf_cap_and_floor():
	assert p.mpf(50000)["mpf_employee"] == 1500 and p.mpf(50000)["mpf_employer"] == 1500
	low = p.mpf(5000)
	assert low["mpf_employee"] == 0 and low["mpf_employer"] == 250 and "7,100" in low["mpf_note"]
	assert p.mpf(7100)["mpf_employee"] == 355


def test_mpf_free_period():
	joined = date(2026, 10, 20)
	assert p.mpf(10000, joined, date(2026, 10, 31))["mpf_employee"] == 0   # free until 18 Nov
	assert p.mpf(10000, joined, date(2026, 11, 30))["mpf_note"].startswith("30-day")
	assert p.mpf(10000, joined, date(2026, 12, 31))["mpf_employee"] == 500


def test_row_net():
	r = p.pay_row(p.MONTHLY, monthly_base=20000)
	assert r["mpf_employee"] == 1000 and r["net"] == 19000
