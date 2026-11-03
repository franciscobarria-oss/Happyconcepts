import frappe
from frappe import _
from frappe.model.document import Document

from happy_kitchen.hk_compliance import scoring


class ChecklistTemplate(Document):
	def validate(self):
		for it in self.items:
			if it.answer_type == "Number" and scoring.bad_limits(it.as_dict()):
				frappe.throw(_("Row {0}: the allowed limits must be numbers, lowest not above highest.").format(it.idx))
			if it.answer_type == "Choice":
				choices = [c.strip() for c in (it.choices or "").splitlines() if c.strip()]
				if len(choices) < 2:
					frappe.throw(_("Row {0}: give at least two choices, one per line.").format(it.idx))
				extra = [c.strip() for c in (it.fail_choices or "").splitlines() if c.strip() and c.strip() not in choices]
				if extra:
					frappe.throw(_("Row {0}: '{1}' is not one of the choices.").format(it.idx, extra[0]))
