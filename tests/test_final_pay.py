from datetime import date

from happy_kitchen.hk_operations import final_pay as f

D = date


def test_leave_year_and_months():
	assert f.leave_year(D(2020, 1, 1), D(2026, 11, 17)) == (D(2026, 1, 1), D(2026, 12, 31))
	assert f.completed_months(D(2026, 1, 1), D(2026, 11, 17)) == 10
	assert f.completed_months(D(2026, 1, 1), D(2026, 11, 30)) == 11


def test_kitty_style_pro_rata():
	# joined years ago (tier 10 days), 10 completed months -> 10 x 10 / 12 = 8.33 -> 8
	r = f.annual_leave_pro_rata(D(2021, 1, 1), D(2026, 11, 17))
	assert (r["tier_days"], r["months"], r["earned"]) == (10, 10, 8)


def test_needs_three_months_and_first_year():
	assert f.annual_leave_pro_rata(D(2026, 9, 1), D(2026, 11, 17))["earned"] == 0  # 2 months
	r = f.annual_leave_pro_rata(D(2026, 3, 1), D(2026, 11, 17))  # 8 months in first year, 7-day tier
	assert (r["tier_days"], r["earned"]) == (7, 5)


def test_not_continuous_gets_nothing():
	assert f.annual_leave_pro_rata(D(2021, 1, 1), D(2026, 11, 17), continuous=False)["earned"] == 0


def test_settle_with_money():
	s = f.settle(D(2021, 1, 1), D(2026, 11, 17), "Monthly", None, annual_taken_final_year=2, sh_given=13,
	             rest_days_owed=2, avg_daily_wage=500)
	assert s["annual"]["net"] == 6
	assert len(s["holidays"]) == 13
	assert [l["days"] for l in s["lines"]] == [6, 0, 2]
	assert s["total_days"] == 8 and s["total_amount"] == 4000


def test_settle_unknown_wage_and_overtaken_leave():
	s = f.settle(D(2021, 1, 1), D(2026, 11, 17), annual_taken_final_year=12, sh_given=10)
	assert s["total_amount"] is None
	assert s["annual"]["net"] == -4
	assert s["lines"][1]["days"] == 3  # 13 holidays, 10 given


def test_daily_wage():
	assert f.daily_wage(monthly_base=18250) == 600.0
	assert f.daily_wage(hourly_rate=80) == 640.0
	assert f.daily_wage(monthly_base=18250, override=700) == 700.0
