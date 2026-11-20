import frappe
from frappe.model.document import Document

from happy_kitchen.recipe_management import cake_math as m


class CakeCosting(Document):
	def validate(self):
		from happy_kitchen.recipe_management import cake_costing as cc

		cc.price_lines(self)
		self.volume_cm3 = round(m.volume_cm3(self.shape or "Round", self.height_cm, self.width_cm, self.length_cm), 1)
		if not self.slices:
			self.slices = m.suggest_slices(self.weight_g)
		t = m.totals([{"qty_g": r.qty_g, "unit_cost": r.unit_cost if r.price_note != "No price" else None, "item_name": r.item_name}
		              for r in self.ingredients], self.labour_cost, self.packaging_cost, self.slices, self.weight_g)
		for k in ("ingredient_cost", "total_cost", "cost_per_slice", "cost_per_100g"):
			self.set(k, t[k])
		self.unpriced = ", ".join(t["unpriced"])
