"""Pay sheet for the payroll provider: name, type, hours, rate, total, bank account."""

import frappe
from frappe import _

from happy_kitchen.hk_operations.pay_sheet_api import _check, sheet_rows


def execute(filters=None):
	_check()
	f = frappe._dict(filters or {})
	if not f.month:
		frappe.throw(_("Choose a month (YYYY-MM)."))
	rows = sheet_rows(f.month)
	cur = "HKD"
	columns = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Name"), "fieldname": "employee_name", "width": 160},
		{"label": _("Type"), "fieldname": "type", "width": 80},
		{"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Currency", "options": cur, "width": 90},
		{"label": _("Basic"), "fieldname": "basic", "fieldtype": "Currency", "options": cur, "width": 100},
		{"label": _("Overtime hours"), "fieldname": "ot_hours", "fieldtype": "Float", "precision": 2, "width": 90},
		{"label": _("Overtime"), "fieldname": "overtime", "fieldtype": "Currency", "options": cur, "width": 100},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "options": cur, "width": 110},
		{"label": _("Employee MPF"), "fieldname": "mpf_employee", "fieldtype": "Currency", "options": cur, "width": 100},
		{"label": _("Net pay"), "fieldname": "net", "fieldtype": "Currency", "options": cur, "width": 110},
		{"label": _("Employer MPF"), "fieldname": "mpf_employer", "fieldtype": "Currency", "options": cur, "width": 100},
		{"label": _("MPF note"), "fieldname": "mpf_note", "width": 220},
		{"label": _("Bank"), "fieldname": "bank_name", "width": 130},
		{"label": _("Bank account"), "fieldname": "bank_ac_no", "width": 150},
		{"label": _("To fix"), "fieldname": "problems", "width": 200},
	]
	return columns, rows
