"""One-off loader for a part-timer timesheet (JSON: [{name, short, rate, shifts: [[date, in, out]]}]).
Creates missing hourly Employees and Employee Checkin IN/OUT rows; safe to run twice.
Run: bench --site <site> execute happy_kitchen.hk_operations.timesheet_load.load --kwargs '{"path": "..."}'
The JSON holds names and hours only, never bank details, and is not kept in the repo."""

import json

import frappe
from frappe.utils import getdate

from happy_kitchen.hk_operations import continuous_api

PLACEHOLDER_DOB = "1990-01-01"


def _employee(p, first_day, company) -> str:
	name = frappe.db.get_value("Employee", {"employee_name": p["name"]})
	if name:
		return name
	first = p["name"].split(",")[-1].strip() if "," in p["name"] else p["name"]
	doc = frappe.get_doc({"doctype": "Employee", "first_name": first, "gender": "Prefer not to say",
	                      "date_of_birth": PLACEHOLDER_DOB, "date_of_joining": first_day, "company": company,
	                      "status": "Active", "hk_short_name": p.get("short") or first.split()[0],
	                      "hk_hourly_rate": p["rate"]})
	doc.insert(ignore_permissions=True)
	return doc.name


def load(path: str, dry_run: bool = False) -> dict:
	company = frappe.defaults.get_global_default("company")
	made = added = 0
	for p in json.load(open(path)):
		if not p["shifts"]:
			continue
		existed = frappe.db.exists("Employee", {"employee_name": p["name"]})
		emp = _employee(p, min(s[0] for s in p["shifts"]), company)
		made += 0 if existed else 1
		for day, t_in, t_out in p["shifts"]:
			for log_type, t in (("IN", t_in), ("OUT", t_out)):
				when = f"{day} {t}:00"
				if frappe.db.exists("Employee Checkin", {"employee": emp, "time": when, "log_type": log_type}):
					continue
				frappe.get_doc({"doctype": "Employee Checkin", "employee": emp, "log_type": log_type, "time": when,
				                "device_id": "Timesheet import"}).insert(ignore_permissions=True)
				added += 1
	end = max(getdate(s[0]) for p in json.load(open(path)) for s in p["shifts"])
	moved = continuous_api.check_all(end, notify=False)
	if dry_run:
		frappe.db.rollback()
	else:
		frappe.db.commit()
	return {"employees_made": made, "checkins_added": added, "reached_or_close": moved}
