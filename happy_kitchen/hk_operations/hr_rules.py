"""HR Phase 1 rules: Employment Ordinance (EO, Cap. 57) leave entitlements, MPF enrolment and
expiry reminders. Plain Python, no frappe (tests/test_hr_rules.py).

SOURCES / STATUS: every rule below is from general knowledge of the EO and Labour Department
guidance (2026-11-17). Each is marked TO CONFIRM until Francisco has checked it against the
Labour Department's current guide; then replace the marker with "Confirmed <date>, <source>"."""

from __future__ import annotations

from datetime import date, timedelta

from happy_kitchen.hk_operations.team import annual_leave_days  # EO s.41AC scale, TO CONFIRM

MONTHLY = "Monthly"
HOURLY = "Hourly part-timer"
CONTRACT_TYPES = (MONTHLY, HOURLY)

# Sickness allowance (EO s.33, 33A): TO CONFIRM
SICK_FIRST_YEAR_PER_MONTH = 2
SICK_AFTER_PER_MONTH = 4
SICK_CAP = 120
SICK_PAY_FRACTION = 0.8  # four fifths of the average daily wages

MATERNITY_DAYS = 98  # 14 weeks (EO s.12), TO CONFIRM
PATERNITY_DAYS = 5  # EO s.15B, TO CONFIRM

MPF_WAIT_DAYS = 60  # employee must join a scheme within 60 days of starting, TO CONFIRM
SUBSTITUTE_HOLIDAY_DAYS = 60  # substitute holiday within 60 days before or after the SH, TO CONFIRM
SH_QUALIFY_MONTHS = 3  # holiday pay after 3 months on a continuous contract, TO CONFIRM

REMIND_DAYS = 30  # expiry reminders start this many days ahead
MPF_REMIND_DAYS = 14


def full_years(joined: date, on: date) -> int:
	return (on.year - joined.year) - ((on.month, on.day) < (joined.month, joined.day))


def is_continuous(contract_type: str | None, continuous_status: str | None) -> bool:
	"""Monthly staff are on a continuous contract; part-timers only while the 468 watch says
	"Reached" (68 hours in 4 weeks)."""
	if contract_type == HOURLY:
		return continuous_status == "Reached"
	return True


def annual_leave_entitlement(joined: date, on: date, continuous: bool = True) -> int:
	return annual_leave_days(joined, on) if continuous else 0


def sick_days_per_month(joined: date, on: date) -> int:
	return SICK_FIRST_YEAR_PER_MONTH if full_years(joined, on) < 1 else SICK_AFTER_PER_MONTH


def sick_days_to_add(joined: date, on: date, balance: float, continuous: bool = True) -> float:
	"""Days to add on the 1st of a month: the monthly accrual, never taking the balance over the cap."""
	if not continuous:
		return 0
	return max(0, min(sick_days_per_month(joined, on), SICK_CAP - balance))


def holiday_pay_qualifies(joined: date, on: date, continuous: bool = True) -> bool:
	"""Statutory holiday pay needs a continuous contract and 3 months of service before the holiday."""
	return continuous and on >= add_months(joined, SH_QUALIFY_MONTHS)


def add_months(d: date, months: int) -> date:
	m = d.month - 1 + months
	y, m = d.year + m // 12, m % 12 + 1
	last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
	return date(y, m, min(d.day, last))


def mpf_enrol_due(joined: date | None) -> date | None:
	return joined + timedelta(days=MPF_WAIT_DAYS) if joined else None


def substitute_deadline(holiday: date) -> date:
	return holiday + timedelta(days=SUBSTITUTE_HOLIDAY_DAYS)


def entitlements(contract_type: str | None, continuous_status: str | None, joined: date | None, on: date) -> list[str]:
	"""Plain-English lines for the Employee card (what applies today)."""
	if not joined:
		return []
	cont = is_continuous(contract_type, continuous_status)
	if not cont:
		return ["Not on a continuous contract yet: no holiday pay, annual leave or sick allowance until 68 hours in 4 weeks is reached"]
	out = []
	al = annual_leave_days(joined, on)
	out.append(f"Annual leave: {al} days a year" if al else "Annual leave: starts after 12 months of service")
	out.append(f"Sick days earned: {sick_days_per_month(joined, on)} a month (up to {SICK_CAP})")
	out.append("Statutory holiday pay: yes" if holiday_pay_qualifies(joined, on) else
	           f"Statutory holiday pay: from {add_months(joined, SH_QUALIFY_MONTHS).isoformat()}")
	return out


def reminders(emp: dict, today: date) -> list[dict]:
	"""Things due soon for one employee. `emp` keys: name, joined, cert_expiry, visa_expiry,
	probation_end, mpf_member_no, mpf_exempt (all optional dates are `date` or None).
	Each result: kind, label, due, days (negative = overdue)."""
	out = []

	def add(kind, label, due, window):
		if due is None:
			return
		days = (due - today).days
		if days <= window:
			out.append({"kind": kind, "label": label, "due": due, "days": days})

	add("cert", "Food-handler certificate expires", emp.get("cert_expiry"), REMIND_DAYS)
	add("visa", "Visa / work permit expires", emp.get("visa_expiry"), REMIND_DAYS)
	add("probation", "Probation ends", emp.get("probation_end"), REMIND_DAYS)
	if not emp.get("mpf_member_no") and not emp.get("mpf_exempt"):
		add("mpf", "MPF enrolment due", mpf_enrol_due(emp.get("joined")), MPF_REMIND_DAYS)
	return sorted(out, key=lambda r: r["days"])
