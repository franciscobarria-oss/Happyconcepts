"""Every checklist run in a date range: who signed, when, late, failed answers, review.
With "Only problems" ticked: missed, late, overdue or with failed answers (the audit view)."""

import frappe
from frappe import _
from frappe.utils import add_days, nowdate


def execute(filters=None):
	f = frappe._dict(filters or {})
	f.from_date = f.from_date or add_days(nowdate(), -6)
	f.to_date = f.to_date or nowdate()
	conds = ["docstatus < 2", "run_date between %(from_date)s and %(to_date)s"]
	if f.area:
		conds.append("area = %(area)s")
	if f.template:
		conds.append("template = %(template)s")
	if f.only_problems:
		conds.append("(status in ('Overdue', 'Missed', 'Completed with issues') or late = 1 or issues > 0)")
	rows = frappe.db.sql(f"""
		select name, run_date, area, title, status, window_end, employee_name, signed_at, late, issues,
			critical_issues, reviewer, reviewed_at
		from `tabChecklist Run` where {" and ".join(conds)}
		order by run_date desc, window_end desc""", f, as_dict=True)
	columns = [
		{"label": _("Run"), "fieldname": "name", "fieldtype": "Link", "options": "Checklist Run", "width": 140},
		{"label": _("Date"), "fieldname": "run_date", "fieldtype": "Date", "width": 100},
		{"label": _("Area"), "fieldname": "area", "fieldtype": "Link", "options": "Check Area", "width": 140},
		{"label": _("Checklist"), "fieldname": "title", "width": 170},
		{"label": _("Status"), "fieldname": "status", "width": 150},
		{"label": _("Due by"), "fieldname": "window_end", "fieldtype": "Datetime", "width": 150},
		{"label": _("Signed by"), "fieldname": "employee_name", "width": 140},
		{"label": _("Signed at"), "fieldname": "signed_at", "fieldtype": "Datetime", "width": 150},
		{"label": _("Late"), "fieldname": "late", "fieldtype": "Check", "width": 60},
		{"label": _("Failed answers"), "fieldname": "issues", "fieldtype": "Int", "width": 110},
		{"label": _("Critical fails"), "fieldname": "critical_issues", "fieldtype": "Int", "width": 100},
		{"label": _("Reviewed by"), "fieldname": "reviewer", "fieldtype": "Link", "options": "User", "width": 150},
	]
	return columns, rows
