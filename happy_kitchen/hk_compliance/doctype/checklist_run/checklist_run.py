import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from happy_kitchen.hk_compliance import schedule, scoring


class ChecklistRun(Document):
	def validate(self):
		tpl = frappe.get_cached_doc("Checklist Template", self.template)
		self.title = self.title or tpl.title
		self.category = self.category or tpl.category
		if self.is_new():
			self.requires_review = tpl.requires_review
		if not self.department and self.area:
			self.department = frappe.db.get_value("Check Area", self.area, "department")
		if not self.answers:
			for row in scoring.answers_from_template([i.as_dict() for i in tpl.items]):
				self.append("answers", row)
		for row in self.answers:
			row.result = scoring.evaluate(row.as_dict())

	def before_submit(self):
		if not self.employee or not self.signed_at:
			frappe.throw(_("Sign the checklist on the Kitchen Checks screen with your PIN."))
		found = scoring.problems([r.as_dict() for r in self.answers])
		if found:
			frappe.throw("<br>".join(problem_message(p) for p in found), title=_("Not finished yet"))
		self.status, self.issues, self.critical_issues = scoring.outcome([r.as_dict() for r in self.answers])
		self.late = int(bool(self.window_end) and schedule.is_late(
			get_datetime(self.signed_at), get_datetime(self.window_end), self.grace_minutes or 0))
		for row in self.answers:
			if not row.answered_by:
				row.answered_by = self.employee
			if not row.answered_at:
				row.answered_at = self.signed_at

	def before_cancel(self):
		if "System Manager" not in frappe.get_roles():
			frappe.throw(_("A signed checklist is an audit record and can't be cancelled."))


def problem_message(p) -> str:
	i, prompt, code = p
	text = {
		"unanswered": _("not answered"),
		"not_number": _("not a number"),
		"bad_choice": _("not one of the choices"),
		"photo": _("photo needed"),
		"corrective": _("failed: say what was done about it"),
	}[code]
	return f"{i}. {prompt}: {text}"


def mark_reviewed(doc, note=None):
	doc.db_set({"status": schedule.REVIEWED, "reviewer": frappe.session.user, "reviewed_at": now_datetime(),
	            "review_note": note or doc.review_note})
