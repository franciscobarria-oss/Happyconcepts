from datetime import date

from happy_kitchen.hk_operations import hr_rules as h

D = date


def test_full_years_and_sick_rate():
	assert h.full_years(D(2025, 3, 10), D(2026, 3, 9)) == 0
	assert h.full_years(D(2025, 3, 10), D(2026, 3, 10)) == 1
	assert h.sick_days_per_month(D(2025, 3, 10), D(2026, 3, 9)) == 2
	assert h.sick_days_per_month(D(2025, 3, 10), D(2026, 3, 10)) == 4


def test_sick_cap():
	assert h.sick_days_to_add(D(2020, 1, 1), D(2026, 1, 1), 100) == 4
	assert h.sick_days_to_add(D(2020, 1, 1), D(2026, 1, 1), 118) == 2
	assert h.sick_days_to_add(D(2020, 1, 1), D(2026, 1, 1), 120) == 0
	assert h.sick_days_to_add(D(2020, 1, 1), D(2026, 1, 1), 5, continuous=False) == 0


def test_continuous_rule():
	assert h.is_continuous(h.MONTHLY, None)
	assert not h.is_continuous(h.HOURLY, "Close")
	assert h.is_continuous(h.HOURLY, "Reached")


def test_annual_leave():
	assert h.annual_leave_entitlement(D(2025, 1, 1), D(2025, 12, 31)) == 0
	assert h.annual_leave_entitlement(D(2025, 1, 1), D(2026, 1, 1)) == 7
	assert h.annual_leave_entitlement(D(2017, 1, 1), D(2026, 1, 1)) == 14
	assert h.annual_leave_entitlement(D(2017, 1, 1), D(2026, 1, 1), continuous=False) == 0


def test_add_months_clamps_month_end():
	assert h.add_months(D(2026, 11, 30), 3) == D(2027, 2, 28)
	assert h.add_months(D(2023, 11, 30), 3) == D(2024, 2, 29)


def test_holiday_pay_needs_three_months():
	assert not h.holiday_pay_qualifies(D(2026, 9, 1), D(2026, 11, 30))
	assert h.holiday_pay_qualifies(D(2026, 9, 1), D(2026, 12, 1))
	assert not h.holiday_pay_qualifies(D(2020, 1, 1), D(2026, 1, 1), continuous=False)


def test_mpf_and_substitute_dates():
	assert h.mpf_enrol_due(D(2026, 11, 1)) == D(2026, 12, 31)
	assert h.mpf_enrol_due(None) is None
	assert h.substitute_deadline(D(2026, 12, 25)) == D(2027, 2, 23)


def test_entitlement_lines():
	assert "Not on a continuous" in h.entitlements(h.HOURLY, "Below", D(2026, 1, 1), D(2026, 11, 17))[0]
	lines = h.entitlements(h.MONTHLY, None, D(2026, 1, 1), D(2026, 11, 17))
	assert lines[0].startswith("Annual leave: starts after 12 months")
	assert "2 a month" in lines[1]
	assert h.entitlements(h.MONTHLY, None, None, D(2026, 11, 17)) == []


def test_reminders():
	today = D(2026, 11, 17)
	emp = {"joined": D(2026, 10, 10), "cert_expiry": D(2026, 12, 1), "visa_expiry": D(2027, 6, 1),
	       "probation_end": D(2026, 11, 10), "mpf_member_no": None}
	r = h.reminders(emp, today)
	assert [x["kind"] for x in r] == ["probation", "cert"]  # MPF due 2026-12-09 is 22 days away, outside 14
	emp["joined"] = D(2026, 9, 20)  # due 2026-11-19
	assert [x["kind"] for x in h.reminders(emp, today)][-1] == "mpf" or "mpf" in [x["kind"] for x in h.reminders(emp, today)]
	emp["mpf_member_no"] = "X1"
	assert "mpf" not in [x["kind"] for x in h.reminders(emp, today)]
