# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""One block of overtime for one person. Submitting = approving (HR Manager).
Payroll stays with the outside provider: the Overtime Summary report gives the
month's approved hours and amounts per person to send them."""

import frappe
from frappe import _
from frappe.model.document import Document

from happy_kitchen.hk_operations import calc


def hourly_amount_for(employee: str, overtime_rate: str) -> float:
	rate = frappe.get_cached_doc("Overtime Rate", overtime_rate)
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["hk_monthly_base", "hk_working_days", "hk_hours_per_day", "hk_hourly_rate"],
		as_dict=True,
	) or frappe._dict()
	wage = calc.own_hourly_wage(emp.hk_monthly_base, emp.hk_working_days, emp.hk_hours_per_day, emp.hk_hourly_rate)
	if rate.method == calc.MULTIPLE and not wage:
		frappe.throw(
			_("{0} has no monthly base / working days / hours per day (or hourly rate) on the Employee record, so a multiple of their wage can't be worked out.").format(employee)
		)
	return calc.overtime_hourly_amount(rate.method, rate.value, wage)


PAY_ROLES = {"System Manager", "HR Manager", "HR User"}


@frappe.whitelist()
def preview(employee: str, overtime_rate: str, hours: float = 0) -> dict:
	"""Per-hour and total for the form, before saving. The amounts reveal the
	person's wage, so only HR (who see the Employee pay fields) get them."""
	frappe.has_permission("Employee", "read", employee, throw=True)
	if not PAY_ROLES.intersection(frappe.get_roles()):
		return {}
	per_hour = hourly_amount_for(employee, overtime_rate)
	return {"hourly_amount": round(per_hour, 2), "amount": calc.overtime_amount(hours, per_hour)}


class OvertimeEntry(Document):
	def before_validate(self):
		if not self.overtime_rate and self.employee:
			self.overtime_rate = frappe.db.get_value("Employee", self.employee, "hk_default_overtime_rate")

	def validate(self):
		if (self.hours or 0) <= 0:
			frappe.throw(_("Hours must be more than 0."))
		if (self.hours or 0) > 16:
			frappe.throw(_("{0} hours of overtime in one day looks wrong. Split it over the right dates.").format(self.hours))
		if not self.overtime_rate:
			frappe.throw(_("Pick a rate (or set a default overtime rate on the Employee)."))
		if frappe.db.get_value("Overtime Rate", self.overtime_rate, "disabled"):
			frappe.throw(_("Overtime Rate {0} is disabled.").format(self.overtime_rate))
		per_hour = hourly_amount_for(self.employee, self.overtime_rate)
		self.hourly_amount = round(per_hour, 2)
		self.amount = calc.overtime_amount(self.hours, per_hour)
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		self.status = "Approved"
		self.approved_by = frappe.session.user

	def on_cancel(self):
		self.db_set("status", "Rejected")
