"""HR Phase 1 server side: Employee card fields, daily leave accrual (annual leave by years of
service, sick days by month), Today "Waiting on you" lines. Rules: hr_rules.py."""

import frappe
from frappe import _
from frappe.utils import add_days, add_years, get_first_day, get_last_day, getdate, nowdate

from happy_kitchen.hk_operations import hr_rules as rules
from happy_kitchen.hk_operations.team import ANNUAL_LEAVE, MANAGER_ROLES

SICK = "Sick Leave"


def employee_validate(doc, method=None):
	"""Worked-out fields on the Employee card."""
	joined = getdate(doc.date_of_joining) if doc.date_of_joining else None
	doc.hk_mpf_enrol_due = rules.mpf_enrol_due(joined)
	if not doc.get("hk_contract_type") and (doc.get("hk_monthly_base") or doc.get("hk_hourly_rate")):
		doc.hk_contract_type = rules.MONTHLY if doc.get("hk_monthly_base") else rules.HOURLY
	doc.hk_entitlements = "\n".join(
		rules.entitlements(doc.get("hk_contract_type"), doc.get("hk_continuous_status"), joined, getdate(nowdate())))


def _staff():
	return frappe.get_all("Employee", filters={"status": "Active"},
	                      fields=["name", "date_of_joining", "hk_contract_type", "hk_continuous_status", "company"])


def _continuous(e) -> bool:
	return rules.is_continuous(e.hk_contract_type, e.hk_continuous_status)


def _allocate(employee, leave_type, days, start, end, note):
	if days <= 0 or not frappe.db.exists("Leave Type", leave_type):
		return None
	if frappe.db.exists("Leave Allocation", {"employee": employee, "leave_type": leave_type, "from_date": start,
	                                         "docstatus": ["<", 2]}):
		return None
	doc = frappe.get_doc({"doctype": "Leave Allocation", "employee": employee, "leave_type": leave_type,
	                      "from_date": start, "to_date": end, "new_leaves_allocated": days,
	                      "carry_forward": 1 if leave_type == SICK else 0, "description": note})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def allocate_leave(on=None) -> list[str]:
	"""Idempotent. Annual leave on each service anniversary (EO scale); sick days once a month,
	topped up to the cap. Only for staff on a continuous contract."""
	on = getdate(on or nowdate())
	made = []
	for e in _staff():
		if not e.date_of_joining or not _continuous(e):
			continue
		joined = getdate(e.date_of_joining)
		years = rules.full_years(joined, on)
		if years >= 1:
			start = add_years(joined, years)
			if start <= on:
				n = _allocate(e.name, ANNUAL_LEAVE, rules.annual_leave_entitlement(joined, on), start,
				              add_days(add_years(joined, years + 1), -1), "Employment Ordinance annual leave")
				if n:
					made.append(n)
		first = get_first_day(on)
		if joined <= on:
			balance = _sick_balance(e.name, on)
			n = _allocate(e.name, SICK, rules.sick_days_to_add(joined, on, balance), first, get_last_day(on),
			              "Employment Ordinance sickness days")
			if n:
				made.append(n)
	return made


def _sick_balance(employee, on) -> float:
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	return get_leave_balance_on(employee, SICK, on) or 0


def scheduled_allocation():
	"""Daily (hooks.py)."""
	allocate_leave()
	frappe.db.commit()


def reminder_rows() -> list[dict]:
	today = getdate(nowdate())
	out = []
	for e in frappe.get_all("Employee", filters={"status": "Active"},
	                        fields=["name", "employee_name", "hk_short_name", "date_of_joining", "hk_cert_expiry",
	                                "hk_visa_expiry", "hk_probation_end", "hk_mpf_member_no"]):
		d = lambda v: getdate(v) if v else None  # noqa: E731
		for r in rules.reminders({"joined": d(e.date_of_joining), "cert_expiry": d(e.hk_cert_expiry),
		                          "visa_expiry": d(e.hk_visa_expiry), "probation_end": d(e.hk_probation_end),
		                          "mpf_member_no": e.hk_mpf_member_no}, today):
			out.append({**r, "employee": e.name, "name": e.hk_short_name or e.employee_name})
	return out


def waiting_lines() -> list[dict]:
	"""Today > Waiting on you: leave to approve and HR reminders."""
	roles = set(frappe.get_roles())
	out = []
	if roles & (set(MANAGER_ROLES) | {"Leave Approver"}):
		n = frappe.db.count("Leave Application", {"status": "Open", "docstatus": 0})
		if n:
			out.append({"label": _("Leave to approve"), "detail": _("{0} applications").format(n),
			            "route": "List/Leave Application?status=Open", "tone": "info"})
	if roles & set(MANAGER_ROLES):
		for r in reminder_rows():
			when = _("overdue") if r["days"] < 0 else _("in {0} days").format(r["days"])
			out.append({"label": f"{_(r['label'])}: {r['name']}", "detail": f"{r['due']} ({when})",
			            "route": f"Form/Employee/{r['employee']}", "tone": "warning" if r["days"] <= 7 else "info"})
	return out
