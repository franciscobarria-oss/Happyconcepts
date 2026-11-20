"""Plain-Python maths for the monthly pay sheet and payment slip (no frappe import;
tests/test_pay_sheet.py).

One row per employee per month: monthly staff are paid their monthly base, hourly staff
hours x hourly rate. Approved overtime is added on top (amount comes from the Overtime Entry,
already worked out with its rate). The slip is information only: the payroll provider's payslip
stays the official one. Statutory holiday pay and MPF lines are not included yet."""

from __future__ import annotations

from datetime import date, datetime

MONTHLY, HOURLY = "Monthly", "Hourly"

# MPF (Mandatory Provident Fund), MPFA mandatory contribution rules: 5 % each from employer and
# employee on relevant income (basic + overtime); the employee pays nothing when the month's
# relevant income is below HK$7,100 (employer still pays); the base is capped at HK$30,000
# (so at most HK$1,500 each); the employee has a 30-day contribution-free period at the start
# (the employer's share is due from day 1). Minimum figure seen on mpfa.org.hk (2026-11-20);
# Francisco / the provider confirm the figures before they are relied on. Review each January.
MPF_RATE = 0.05
MPF_MIN_INCOME = 7100.0
MPF_MAX_INCOME = 30000.0
MPF_FREE_DAYS = 30


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


def mpf(relevant_income, joined=None, last_day=None) -> dict:
	"""Employee and employer MPF for the month. `joined` / `last_day` (dates) apply the 30-day
	contribution-free period when the whole month falls inside it (a month that only partly
	does is flagged for a person to check, not guessed)."""
	income = flt(relevant_income)
	base = min(income, MPF_MAX_INCOME)
	employer = money(base * MPF_RATE)
	employee = money(base * MPF_RATE) if income >= MPF_MIN_INCOME else 0.0
	note = "" if income >= MPF_MIN_INCOME else "Below HK$7,100: no employee MPF"
	if joined and last_day:
		free_until = date.fromordinal(joined.toordinal() + MPF_FREE_DAYS - 1)
		first = date(last_day.year, last_day.month, 1)
		if last_day <= free_until:
			employee, note = 0.0, "First 30 days: no employee MPF"
		elif first <= free_until:
			note = "30-day free period ends this month: check employee MPF"
	return {"mpf_employee": employee, "mpf_employer": employer, "mpf_note": note}


def pay_row(kind, monthly_base=0, hourly_rate=0, hours=0, ot_hours=0, ot_amount=0, joined=None,
            last_day=None) -> dict:
	"""Pay for the month. Monthly: base salary (hours shown for information). Hourly: hours x rate.
	Total is the relevant income for MPF; net is total less the employee MPF."""
	hours, ot_hours = round(flt(hours), 2), round(flt(ot_hours), 2)
	if kind == MONTHLY:
		rate, basic = money(monthly_base), money(monthly_base)
	else:
		rate, basic = flt(hourly_rate), money(flt(hours) * flt(hourly_rate))
	overtime = money(ot_amount)
	total = money(basic + overtime)
	row = {"type": kind, "hours": hours, "rate": rate, "basic": basic, "ot_hours": ot_hours,
	       "overtime": overtime, "total": total}
	row.update(mpf(total, joined, last_day))
	row["net"] = money(total - row["mpf_employee"])
	return row


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
