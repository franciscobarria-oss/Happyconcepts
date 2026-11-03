import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from happy_kitchen.hk_compliance import schedule


class ChecklistSchedule(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if self.active and (not before or not before.active):
			self.active_from = now_datetime()  # runs start from this moment, not from earlier windows
		elif not self.active:
			self.active_from = None
		self.title = f"{self.template} · {self.area}"
		if self.frequency == "Every N hours" and (self.every_hours or 0) < 1:
			frappe.throw(_("Set how many hours between checks (1 or more)."))
		if self.frequency == "Monthly" and not 1 <= (self.day_of_month or 0) <= 31:
			frappe.throw(_("Day of month must be between 1 and 31."))
		if self.frequency == "Selected weekdays" and not self.weekdays():
			frappe.throw(_("Tick at least one day."))
		if not self.department and self.area:
			self.department = frappe.db.get_value("Check Area", self.area, "department")
		schedule.windows(self.as_rule(), frappe.utils.getdate())  # raises on a bad rule

	def weekdays(self) -> set[str]:
		return {d for d in schedule.WEEKDAYS if self.get(d.lower())}

	def as_rule(self) -> dict:
		return as_rule(self)


def as_rule(row) -> dict:
	"""The pure schedule dict (hk_compliance/schedule.py) for a Checklist Schedule doc or db row."""
	return {
		"frequency": row.get("frequency"),
		"weekdays": {d for d in schedule.WEEKDAYS if row.get(d.lower())},
		"day_of_month": row.get("day_of_month"),
		"start_time": row.get("start_time"),
		"due_time": row.get("due_time"),
		"every_hours": row.get("every_hours"),
		"grace_minutes": row.get("grace_minutes"),
	}
