"""Monthly pay sheet and payment slip: hourly row from check-ins, monthly row, problems. Rolls back."""

import frappe
from frappe.utils import add_days, get_first_day, nowdate

from happy_kitchen.hk_operations import pay_sheet_api


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	try:
		day = add_days(get_first_day(nowdate()), 1)
		month = str(day)[:7]
		hourly = frappe.get_doc({"doctype": "Employee", "first_name": "E2E-PayH", "gender": "Prefer not to say",
		                         "date_of_birth": "1990-01-01", "date_of_joining": add_days(day, -60), "company": company,
		                         "status": "Active", "hk_hourly_rate": 80}).insert(set_name="E2E-PAY-H")
		monthly = frappe.get_doc({"doctype": "Employee", "first_name": "E2E-PayM", "gender": "Prefer not to say",
		                          "date_of_birth": "1990-01-01", "date_of_joining": add_days(day, -60), "company": company,
		                          "status": "Active", "hk_monthly_base": 15000, "bank_ac_no": "123"}).insert(set_name="E2E-PAY-M")
		for t, lt in (("08:00:00", "IN"), ("14:30:00", "OUT")):
			frappe.get_doc({"doctype": "Employee Checkin", "employee": hourly.name, "log_type": lt, "time": f"{day} {t}"}).insert()
		by = {r["employee"]: r for r in pay_sheet_api.sheet_rows(month)}
		_check(by["E2E-PAY-H"]["hours"] == 6.5 and by["E2E-PAY-H"]["total"] == 520, "hourly 6.5 h x 80")
		_check("No bank account" in by["E2E-PAY-H"]["problems"], "missing bank flagged")
		_check(by["E2E-PAY-M"]["total"] == 15000 and not by["E2E-PAY-M"]["problems"], "monthly base, no problems")
	finally:
		frappe.db.rollback()
	print("pay sheet e2e OK")
