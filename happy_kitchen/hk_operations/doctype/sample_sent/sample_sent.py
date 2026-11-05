import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class SampleSent(Document):
	def validate(self):
		if not self.sample_date:
			self.sample_date = nowdate()
		if flt(self.qty) <= 0:
			frappe.throw(_("Quantity must be more than zero."))
		if not (self.customer or self.recipient):
			frappe.throw(_("Say who the sample went to: pick a customer or type a name."))
		info = frappe.db.get_value("Item", self.item, ["item_name", "stock_uom"], as_dict=True) or {}
		self.item_name = info.get("item_name") or self.item_name
		if not self.uom:
			self.uom = info.get("stock_uom")
		if not self.sent_by:
			self.sent_by = frappe.session.user
		# quantity in the item's stock unit, which is what the day's needs count
		factor = 1.0
		if self.uom and info.get("stock_uom") and self.uom != info.get("stock_uom"):
			factor = flt(frappe.db.get_value("UOM Conversion Detail", {"parent": self.item, "uom": self.uom}, "conversion_factor")) or 1.0
		self.stock_qty = flt(self.qty) * factor
