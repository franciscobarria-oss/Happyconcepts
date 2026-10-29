# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OEMSpecSheet(Document):
	def on_update(self):
		# only one approved version per client product: approving this one supersedes the others
		if self.status == "Approved":
			for name in frappe.get_all(
				"OEM Spec Sheet",
				filters={"customer": self.customer, "item": self.item, "status": "Approved", "name": ("!=", self.name)},
				pluck="name",
			):
				frappe.db.set_value("OEM Spec Sheet", name, "status", "Superseded")
