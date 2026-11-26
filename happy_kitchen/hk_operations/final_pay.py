"""Final pay (leaver) calculation: what is owed when someone leaves. Plain Python, no frappe
(tests/test_final_pay.py). Rules from hr_rules.py / team.py.

ASSUMPTIONS (Francisco signs off; review every January):
- Leave year = from the latest service anniversary on or before the last day (EO default).
- Annual leave in the final year is pro rata by COMPLETED months of service in that year, using the
  days of the tier the person would reach at the end of that year (first year: 7 days), rounded to the
  nearest whole day (half up), and only once 3 months of that year are done. Unused leave from earlier
  years is added.
- Daily wage = average daily wage; the caller may override it (monthly: base x 12 / 365 estimate;
  hourly: hourly rate x hours per day).
- Statutory holidays from the joining date (or 1 Jan) to the last day; owed = qualifying holidays minus
  those given, paid at the daily wage (3 months' continuous service at the holiday).
- Rest days owed (roster "OFF n/12" balance) are a house promise, shown as days and money."""

from __future__ import annotations

import math
from datetime import date, timedelta

from happy_kitchen.hk_operations import hr_rules as rules
from happy_kitchen.hk_operations.team import HOLIDAYS, annual_leave_days, flt

MIN_MONTHS_FOR_LEAVE = 3


def round_half_up(x: float) -> int:
	return int(math.floor(x + 0.5))


def leave_year(joined: date, last_day: date) -> tuple[date, date]:
	"""Start and end of the leave year that contains the last day."""
	years = rules.full_years(joined, last_day)
	start = rules.add_months(joined, 12 * years)
	return start, rules.add_months(start, 12) - timedelta(days=1)


def completed_months(start: date, last_day: date) -> int:
	"""Whole months served from start up to and including the last day."""
	n = 0
	while rules.add_months(start, n + 1) <= last_day + timedelta(days=1):
		n += 1
	return n


def annual_leave_pro_rata(joined: date, last_day: date, continuous: bool = True) -> dict:
	start, end = leave_year(joined, last_day)
	months = min(completed_months(start, last_day), 12)
	tier_on = end if rules.full_years(joined, last_day) >= 1 else rules.add_months(joined, 12)
	tier = annual_leave_days(joined, tier_on) if continuous else 0
	days = 0
	if continuous and months >= MIN_MONTHS_FOR_LEAVE:
		days = round_half_up(tier * months / 12)
	return {"year_start": start, "year_end": end, "months": months, "tier_days": tier, "earned": days}


def holidays_between(start: date, end: date) -> list[date]:
	return sorted(d for d in (date.fromisoformat(k) for k in HOLIDAYS) if start <= d <= end)


def daily_wage(monthly_base=0, hourly_rate=0, hours_per_day=8, override=0) -> float:
	if flt(override) > 0:
		return round(flt(override), 2)
	if flt(monthly_base) > 0:
		return round(flt(monthly_base) * 12 / 365, 2)
	if flt(hourly_rate) > 0:
		return round(flt(hourly_rate) * (flt(hours_per_day) or 8), 2)
	return 0.0


def settle(joined: date, last_day: date, contract_type=None, continuous_status=None, annual_taken_final_year=0,
           annual_unused_before=0, sh_given=0, rest_days_owed=0, avg_daily_wage=0) -> dict:
	"""Everything owed at leaving. Money lines are None when the daily wage is unknown."""
	continuous = rules.is_continuous(contract_type, continuous_status)
	al = annual_leave_pro_rata(joined, last_day, continuous)
	al_net = round(al["earned"] + flt(annual_unused_before) - flt(annual_taken_final_year), 2)
	hol = [h for h in holidays_between(max(joined, date(last_day.year, 1, 1)), last_day)]
	qualifying = [h for h in hol if rules.holiday_pay_qualifies(joined, h, continuous)]
	sh_owed = max(0, len(qualifying) - int(flt(sh_given)))
	wage = flt(avg_daily_wage)
	money = (lambda d: round(d * wage, 2)) if wage > 0 else (lambda d: None)
	lines = [
		{"item": "Annual leave owed (net)", "days": al_net, "amount": money(max(al_net, 0)),
		 "note": f"{al['earned']} earned ({al['months']} months of {al['tier_days']} days) + "
		         f"{flt(annual_unused_before)} brought forward - {flt(annual_taken_final_year)} taken"},
		{"item": "Statutory holidays not given", "days": sh_owed, "amount": money(sh_owed),
		 "note": f"{len(qualifying)} qualifying, {int(flt(sh_given))} given"},
		{"item": "Rest days owed", "days": flt(rest_days_owed), "amount": money(flt(rest_days_owed)),
		 "note": "Roster balance (house promise, not statutory)"},
	]
	days_paid = max(al_net, 0) + sh_owed + flt(rest_days_owed)
	return {"continuous": continuous, "annual": {**al, "net": al_net}, "holidays": [h.isoformat() for h in hol],
	        "lines": lines, "total_days": round(days_paid, 2), "total_amount": money(days_paid),
	        "daily_wage": wage or None}
