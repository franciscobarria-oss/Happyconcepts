"""Plain-Python maths for the monthly pay sheet and payment slip (no frappe import;
tests/test_pay_sheet.py).

One row per employee per month: monthly staff are paid their monthly base, hourly staff
hours x hourly rate. Approved overtime is added on top (amount comes from the Overtime Entry,
already worked out with its rate). The slip is information only: the payroll provider's payslip
stays the official one. Statutory holiday pay and MPF lines are not included yet."""

from __future__ import annotations

from datetime import date, datetime

MONTHLY, HOURLY = "Monthly", "Hourly"


def flt(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def money(value) -> float:
	return round(flt(value) + 1e-9, 2)


def month_bounds(month: str) -> tuple[date, date]:
	"""'2026-10' -> (2026-10-01, 2026-10-31)."""
	year, mon = (int(p) for p in month.split("-"))
	first = date(year, mon, 1)
	nxt = date(year + (mon == 12), mon % 12 + 1, 1)
	return first, date.fromordinal(nxt.toordinal() - 1)


def worked_hours(checkins: list[tuple[str, datetime]], first: date, last: date) -> float:
	"""Hours from IN/OUT pairs whose IN falls in [first, last] (oldest first or not)."""
	total, start = 0.0, None
	for log_type, when in sorted(checkins, key=lambda c: c[1]):
		if log_type == "IN":
			start = when
		elif log_type == "OUT" and start is not None:
			if first <= start.date() <= last and when > start:
				total += (when - start).total_seconds() / 3600
			start = None
	return round(total, 2)


def contract_type(declared, monthly_base, hourly_rate) -> str:
	if declared in (MONTHLY, HOURLY):
		return declared
	return MONTHLY if flt(monthly_base) else HOURLY


def pay_row(kind, monthly_base=0, hourly_rate=0, hours=0, ot_hours=0, ot_amount=0) -> dict:
	"""Pay for the month. Monthly: base salary (hours shown for information). Hourly: hours x rate."""
	hours, ot_hours = round(flt(hours), 2), round(flt(ot_hours), 2)
	if kind == MONTHLY:
		rate, basic = money(monthly_base), money(monthly_base)
	else:
		rate, basic = flt(hourly_rate), money(flt(hours) * flt(hourly_rate))
	overtime = money(ot_amount)
	return {"type": kind, "hours": hours, "rate": rate, "basic": basic, "ot_hours": ot_hours,
	        "overtime": overtime, "total": money(basic + overtime)}


def problems(row: dict) -> list[str]:
	"""Gaps a person should fix before sending the sheet on."""
	out = []
	if not row.get("rate"):
		out.append("No rate set")
	if row.get("type") == HOURLY and not row.get("hours"):
		out.append("No hours")
	if not row.get("bank_ac_no"):
		out.append("No bank account")
	return out
