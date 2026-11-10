"""468 watch: hours from check-ins, status, one alert per step up, Today line. Rolls back."""

import frappe
from frappe.utils import add_days, nowdate

from happy_kitchen.hk_operations import continuous_api


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	try:
		emp = frappe.get_doc({"doctype": "Employee", "first_name": "E2E-Part", "gender": "Prefer not to say",
		                      "date_of_birth": "1990-01-01", "date_of_joining": add_days(nowdate(), -40), "company": company,
		                      "status": "Active", "hk_hourly_rate": 80}).insert()
		for i in range(1, 7):  # 6 x 9 h = 54 h
			day = add_days(nowdate(), -i)
			for t, lt in (("07:30:00", "IN"), ("16:30:00", "OUT")):
				frappe.get_doc({"doctype": "Employee Checkin", "employee": emp.name, "log_type": lt, "time": f"{day} {t}"}).insert()
		_check(continuous_api.hours_for(emp.name) == 54.0, "54 hours")
		_check(not [m for m in continuous_api.check_all(notify=False) if m["employee"] == emp.name], "54 h is still below")
		day = add_days(nowdate(), -8)
		for t, lt in (("07:30:00", "IN"), ("12:30:00", "OUT")):
			frappe.get_doc({"doctype": "Employee Checkin", "employee": emp.name, "log_type": lt, "time": f"{day} {t}"}).insert()
		moved = [m for m in continuous_api.check_all(notify=False) if m["employee"] == emp.name]
		_check(moved and moved[0]["status"] == "Close", "59 h is Close")
		_check(not [m for m in continuous_api.check_all(notify=False) if m["employee"] == emp.name], "no second alert")
		day = add_days(nowdate(), -9)
		for t, lt in (("07:30:00", "IN"), ("17:30:00", "OUT")):
			frappe.get_doc({"doctype": "Employee Checkin", "employee": emp.name, "log_type": lt, "time": f"{day} {t}"}).insert()
		moved = [m for m in continuous_api.check_all(notify=False) if m["employee"] == emp.name]
		_check(moved and moved[0]["status"] == "Reached", "69 h is Reached")
		_check(any(emp.employee_name.split()[0] in l["label"] or "E2E-Part" in l["label"] for l in continuous_api.waiting_lines()),
		       "Today line")
	finally:
		frappe.db.rollback()
	print("continuous e2e OK")
