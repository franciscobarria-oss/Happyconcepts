"""Monthly pay sheet and payment slip (server side). Maths: pay_sheet.py. Pay and bank fields are
permlevel 1, so only HR Manager / System Manager can open the sheet or a slip. The slip is for
information; the provider's payslip stays the official one."""

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate

from happy_kitchen.hk_operations import pay_sheet as rules
from happy_kitchen.hk_operations.team import HOLIDAY_LIST, MANAGER_ROLES

FIELDS = ["name", "employee_name", "hk_contract_type", "hk_monthly_base", "hk_hourly_rate",
          "bank_name", "bank_ac_no", "date_of_joining", "relieving_date"]


def _check():
	if not set(frappe.get_roles()) & set(MANAGER_ROLES):
		frappe.throw(_("Only HR Manager or System Manager can open pay figures."), frappe.PermissionError)


def _employees(month, employee=None):
	first, last = rules.month_bounds(month)
	filters = {"employee": employee} if employee else {}
	rows = frappe.get_all("Employee", filters={"name": employee} if employee else {}, fields=FIELDS,
	                      order_by="employee_name")
	return [e for e in rows if (not e.date_of_joining or getdate(e.date_of_joining) <= last)
	        and (not e.relieving_date or getdate(e.relieving_date) >= first)]


def sheet_rows(month, employee=None) -> list[dict]:
	first, last = rules.month_bounds(month)
	out = []
	for e in _employees(month, employee):
		# one extra day so an overnight shift that starts on the last day still finds its OUT
		checkins = [(c.log_type, c.time) for c in frappe.get_all(
			"Employee Checkin", filters={"employee": e.name, "time": ["between", [first, add_days(last, 1)]]},
			fields=["log_type", "time"], order_by="time")]
		ot = frappe.db.sql(
			"select coalesce(sum(hours),0), coalesce(sum(amount),0) from `tabOvertime Entry` "
			"where docstatus=1 and employee=%s and date between %s and %s", (e.name, first, last))[0]
		kind = rules.contract_type(e.hk_contract_type, e.hk_monthly_base, e.hk_hourly_rate)
		row = rules.pay_row(kind, e.hk_monthly_base, e.hk_hourly_rate, rules.worked_hours(checkins, first, last),
		                    ot[0], ot[1])
		row.update({"employee": e.name, "employee_name": e.employee_name, "bank_name": e.bank_name,
		            "bank_ac_no": e.bank_ac_no})
		row["problems"] = ", ".join(rules.problems(row))
		out.append(row)
	return out


@frappe.whitelist()
def rows(month):
	_check()
	return sheet_rows(month)


def _extras(employee, month):
	first, last = rules.month_bounds(month)
	leave = frappe.db.sql(
		"select leave_type, sum(total_leave_days) from `tabLeave Application` where docstatus=1 and "
		"status='Approved' and employee=%s and from_date <= %s and to_date >= %s group by leave_type",
		(employee, last, first))
	holidays = frappe.get_all("Holiday", filters={"parent": HOLIDAY_LIST, "holiday_date": ["between", [first, last]]},
	                          fields=["holiday_date", "description"], order_by="holiday_date")
	balances = frappe.db.sql(
		"select leave_type, sum(new_leaves_allocated) from `tabLeave Allocation` where docstatus=1 and employee=%s "
		"and from_date <= %s and to_date >= %s group by leave_type", (employee, last, first))
	return leave, holidays, balances


@frappe.whitelist()
def slip(employee, month):
	"""Bilingual PDF payment slip for one employee and month."""
	_check()
	row = sheet_rows(month, employee)
	if not row:
		frappe.throw(_("No such employee for that month."))
	leave, holidays, balances = _extras(employee, month)
	html = frappe.render_template("happy_kitchen/templates/pay_slip.html", {
		"r": row[0], "month": month, "leave": leave, "holidays": holidays, "balances": balances,
		"company": frappe.defaults.get_global_default("company") or "", "formatdate": formatdate})
	from frappe.utils.pdf import get_pdf
	frappe.local.response.filename = f"payment-slip-{employee}-{month}.pdf"
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "pdf"
