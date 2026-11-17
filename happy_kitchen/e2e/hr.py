"""HR Phase 1: Employee card fields, leave types, checklists, leave accrual, reminders. Rolls back."""

import frappe
from frappe.utils import add_days, add_years, nowdate

from happy_kitchen.hk_operations import hr_api


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	try:
		for lt in ("Annual Leave", "Sick Leave", "Maternity Leave", "Paternity Leave", "Unpaid Leave", "Substitute Holiday"):
			_check(frappe.db.exists("Leave Type", lt), f"leave type {lt}")
		_check(frappe.db.exists("Employee Onboarding Template", "HK New Starter"), "onboarding template")
		_check(frappe.db.exists("Employee Separation Template", "HK Leaver"), "separation template")

		joined = add_days(add_years(nowdate(), -3), -10)  # 3 full years of service: 8 days annual leave
		emp = frappe.get_doc({"doctype": "Employee", "first_name": "E2E-HR", "gender": "Prefer not to say",
		                      "date_of_birth": "1990-01-01", "date_of_joining": joined, "company": company,
		                      "status": "Active", "hk_monthly_base": 20000, "hk_visa_expiry": add_days(nowdate(), 10)}).insert()
		_check(emp.hk_contract_type == "Monthly", "contract type from monthly base")
		_check(str(emp.hk_mpf_enrol_due) == str(add_days(joined, 60)), "MPF enrolment due 60 days after joining")
		_check("Annual leave: 8 days" in emp.hk_entitlements, "entitlement line")

		made = hr_api.allocate_leave()
		allocs = frappe.get_all("Leave Allocation", filters={"employee": emp.name, "docstatus": 1},
		                        fields=["leave_type", "new_leaves_allocated"])
		by = {a.leave_type: a.new_leaves_allocated for a in allocs}
		_check(by.get("Annual Leave") == 8, f"annual leave 8, got {by}")
		_check(by.get("Sick Leave") == 4, f"sick 4, got {by}")
		hr_api.allocate_leave()
		_check(frappe.db.count("Leave Allocation", {"employee": emp.name, "docstatus": 1}) == 2, "allocation is idempotent")

		rows = [r for r in hr_api.reminder_rows() if r["employee"] == emp.name]
		kinds = {r["kind"] for r in rows}
		_check({"visa", "mpf"} <= kinds, f"reminders {kinds}")
		_check(any("Visa" in l["label"] for l in hr_api.waiting_lines()), "Today line for visa")

		part = frappe.get_doc({"doctype": "Employee", "first_name": "E2E-HR-Part", "gender": "Prefer not to say",
		                       "date_of_birth": "1990-01-01", "date_of_joining": joined, "company": company,
		                       "status": "Active", "hk_hourly_rate": 80}).insert()
		_check(part.hk_contract_type == "Hourly part-timer", "hourly contract type")
		hr_api.allocate_leave()
		_check(not frappe.db.count("Leave Allocation", {"employee": part.name}), "no leave before 468 is reached")
		print("hr e2e: ok")
	finally:
		frappe.db.rollback()
