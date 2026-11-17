"""HR Phase 1 setup, idempotent: leave types, onboarding / offboarding checklists, contract
type backfill and the holiday list on every employee. Rules: hk_operations/hr_rules.py."""

import frappe

from happy_kitchen.hk_operations import hr_rules as r
from happy_kitchen.hk_operations import team as t

SICK = "Sick Leave"
MATERNITY = "Maternity Leave"
PATERNITY = "Paternity Leave"
UNPAID = "Unpaid Leave"
SUBSTITUTE = "Substitute Holiday"

# name: fields (only fields the installed HRMS version has are set)
LEAVE_TYPES = {
	t.ANNUAL_LEAVE: {"is_carry_forward": 1, "include_holiday": 0},
	# earns 2 or 4 days a month (hr_api.allocate_leave), up to 120, paid at four fifths
	SICK: {"max_leaves_allowed": r.SICK_CAP, "is_carry_forward": 1, "include_holiday": 1, "is_ppl": 1,
	       "fraction_of_daily_salary_per_leave": r.SICK_PAY_FRACTION},
	MATERNITY: {"max_leaves_allowed": r.MATERNITY_DAYS, "include_holiday": 1},
	PATERNITY: {"max_leaves_allowed": r.PATERNITY_DAYS, "include_holiday": 0},
	UNPAID: {"is_lwp": 1, "include_holiday": 0},
	SUBSTITUTE: {"max_leaves_allowed": 5, "include_holiday": 0},
}

ONBOARDING = ("HK New Starter", [
	"Sign employment contract", "Enrol in MPF scheme (within 60 days)", "Send IR56E to IRD (within 3 months)",
	"Issue uniform", "Food-handler certificate", "Set clock-in PIN", "Confirm contract type and pay",
])
OFFBOARDING = ("HK Leaver", [
	"Final pay and untaken annual leave", "Send IR56F / IR56G to IRD (1 month before last day)",
	"Return uniform and keys", "Disable clock-in PIN", "Tell MPF trustee",
])


def _leave_types():
	meta = frappe.get_meta("Leave Type")
	for name, vals in LEAVE_TYPES.items():
		fields = {k: v for k, v in vals.items() if meta.has_field(k)}
		if frappe.db.exists("Leave Type", name):
			continue  # never overwrite what HR changed by hand
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": name, **fields}).insert(ignore_permissions=True)


def _template(doctype, title, activities):
	"""The templates are named by a series (HR-EMP-ONT-.#####) and need a title, so look them up by title."""
	if frappe.db.exists(doctype, {"title": title}):
		return
	company = frappe.defaults.get_global_default("company")
	doc = frappe.get_doc({"doctype": doctype, "title": title, "company": company, "activities": [
		{"activity_name": a, "role": "HR Manager", "duration": 7} for a in activities]})
	doc.insert(ignore_permissions=True)


def _employees():
	holiday = t.HOLIDAY_LIST if frappe.db.exists("Holiday List", t.HOLIDAY_LIST) else None
	for e in frappe.get_all("Employee", fields=["name", "holiday_list", "hk_contract_type", "hk_monthly_base",
	                                              "hk_hourly_rate"]):
		if not e.hk_contract_type and (e.hk_monthly_base or e.hk_hourly_rate):
			frappe.db.set_value("Employee", e.name, "hk_contract_type",
			                    r.MONTHLY if e.hk_monthly_base else r.HOURLY, update_modified=False)
		if holiday and not e.holiday_list:
			frappe.db.set_value("Employee", e.name, "holiday_list", holiday, update_modified=False)


def execute():
	_leave_types()
	for doctype, spec in (("Employee Onboarding Template", ONBOARDING), ("Employee Separation Template", OFFBOARDING)):
		try:  # a template problem must not stop the migrate
			_template(doctype, *spec)
		except Exception:
			frappe.log_error(title=f"hr_setup: {doctype}")
	_employees()
