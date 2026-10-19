# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from happy_kitchen.hk_operations.calc import FIXED, MULTIPLE


class OvertimeRate(Document):
	def validate(self):
		if self.method not in (FIXED, MULTIPLE):
			frappe.throw(_("Pick a method: {0} or {1}.").format(FIXED, MULTIPLE))
		if (self.value or 0) <= 0:
			frappe.throw(_("Value must be more than 0."))
