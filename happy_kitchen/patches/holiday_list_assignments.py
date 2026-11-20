"""Frappe HR v16 no longer reads Employee.holiday_list or the Company default: salary slips,
attendance and leave all ask for a submitted Holiday List Assignment ("No Holiday List was found
for Employee ... Please assign through Holiday List Assignment"). Assign HK Statutory 2026-27 to the
company (covers new staff) and to every employee, from the list's start date. Idempotent."""

import frappe

from happy_kitchen.hk_operations import team as t


def _assign(applicable_for, name, company):
	if frappe.db.exists("Holiday List Assignment", {"applicable_for": applicable_for, "assigned_to": name,
	                                                "holiday_list": t.HOLIDAY_LIST, "docstatus": 1}):
		return
	frappe.get_doc({"doctype": "Holiday List Assignment", "applicable_for": applicable_for, "assigned_to": name,
	                "holiday_list": t.HOLIDAY_LIST, "from_date": t.HOLIDAY_LIST_RANGE[0],
	                "employee_company": company}).submit()


def execute():
	if not frappe.db.exists("Holiday List", t.HOLIDAY_LIST):
		return
	company = frappe.defaults.get_global_default("company")
	if company:
		_assign("Company", company, company)
	for e in frappe.get_all("Employee", fields=["name", "company"]):
		_assign("Employee", e.name, e.company)
