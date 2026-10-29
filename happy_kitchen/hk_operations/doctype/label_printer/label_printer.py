import frappe
from frappe.model.document import Document
from frappe.utils import flt

KITCHEN_USE = "Kitchen date labels"
KITCHEN_SIZE = (50, 30)  # mm, the SATO's default roll
PRODUCT_SIZE = (100, 150)


class LabelPrinter(Document):
	def validate(self):
		# A new kitchen printer still at the product-label size gets the small roll size.
		if self.label_use == KITCHEN_USE and (flt(self.width_mm), flt(self.height_mm)) in (PRODUCT_SIZE, (0, 0)):
			self.width_mm, self.height_mm = KITCHEN_SIZE
