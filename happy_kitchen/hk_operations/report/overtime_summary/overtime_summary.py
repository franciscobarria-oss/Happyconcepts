# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Approved overtime per person per month: the figures to send to the payroll provider."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	f = frappe._dict(filters or {})
	conditions = ["docstatus = 1", "date between %(from_date)s and %(to_date)s"]
	if f.employee:
		conditions.append("employee = %(employee)s")
	if f.department:
		conditions.append("department = %(department)s")
	rows = frappe.db.sql(
		f"""
		select employee, employee_name, department, date_format(date, '%%Y-%%m') as month,
			sum(hours) as hours, sum(amount) as amount, count(*) as entries,
			group_concat(distinct overtime_rate order by overtime_rate separator ', ') as rates
		from `tabOvertime Entry`
		where {" and ".join(conditions)}
		group by employee, employee_name, department, month
		order by month, employee_name""",
		f,
		as_dict=True,
	)
	pending = frappe.db.count(
		"Overtime Entry", {"docstatus": 0, "date": ("between", [f.from_date, f.to_date])}
	)
	columns = [
		{"label": _("Month"), "fieldname": "month", "width": 90},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Name"), "fieldname": "employee_name", "width": 170},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 150},
		{"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "precision": 2, "width": 90},
		{"label": _("Amount (HK$)"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Entries"), "fieldname": "entries", "fieldtype": "Int", "width": 80},
		{"label": _("Rates"), "fieldname": "rates", "width": 180},
	]
	summary = [
		{"label": _("Approved hours"), "value": sum(flt(r.hours) for r in rows), "datatype": "Float", "indicator": "Blue"},
		{"label": _("Approved amount"), "value": sum(flt(r.amount) for r in rows), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Still to approve"), "value": pending, "datatype": "Int", "indicator": "Orange" if pending else "Green"},
	]
	return columns, rows, None, None, summary
