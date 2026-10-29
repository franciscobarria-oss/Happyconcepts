# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from happy_kitchen.recipe_management import costing
from happy_kitchen.recipe_management.pricing import (
	SUB_RECIPE_TYPES,
	get_ingredient_prices,
	get_packaging_groups,
	get_selling_price,
	get_settings,
	get_working_recipe,
)


class Recipe(Document):
	def before_insert(self):
		if not self.overheads:
			for row in get_settings().default_overheads:
				self.append("overheads", {"service": row.service, "basis": row.basis, "rate": row.rate, "notes": row.notes})

	def validate(self):
		settings = get_settings()
		self.set_ingredient_prices(settings)
		# batch preparations can be sold as-is too (e.g. cookie dough), when their item is a sales item
		if not self.selling_price and (
			self.recipe_type == "Finished Product" or frappe.db.get_value("Item", self.item, "is_sales_item")
		):
			self.selling_price = get_selling_price(self.item, settings.selling_price_list)
		self.calculate_costs(settings)
		self.used_in_recipes = ", ".join(
			frappe.get_all(
				"Recipe Ingredient",
				filters={"parenttype": "Recipe", "item": self.item, "parent": ("!=", self.name)},
				pluck="parent",
				distinct=True,
				order_by="parent",
			)
		)

	def on_update(self):
		self.sync_item_valuation_rate()
		# a working recipe's / component's cost feeds the recipes that use it
		if self.recipe_type in SUB_RECIPE_TYPES and not self.flags.from_recost:
			frappe.enqueue(
				"happy_kitchen.recipe_management.doctype.recipe.recipe.recost_recipes",
				item_code=self.item,
				queue="short",
				enqueue_after_commit=True,
			)

	def sync_item_valuation_rate(self):
		"""A stocked batch preparation's Item gets its ingredient cost per unit as the fallback
		valuation rate, so ERPNext can value it before any stock of it exists (e.g. dough made
		and used in the same Production Log). Labour and overheads are not stock value."""
		if self.recipe_type != "Batch Preparation" or not self.item:
			return
		item = frappe.db.get_value("Item", self.item, ["stock_uom", "valuation_rate", "is_stock_item"], as_dict=True)
		if not item or not item.is_stock_item or (self.yield_uom and self.yield_uom != item.stock_uom):
			return
		rate = flt(self.ingredient_cost_per_unit, 6)
		if rate and abs(flt(item.valuation_rate) - rate) > 1e-9:
			frappe.db.set_value("Item", self.item, "valuation_rate", rate, update_modified=False)

	def set_ingredient_prices(self, settings):
		packaging_groups = get_packaging_groups(settings)
		self.missing_price_count = 0
		for row in self.ingredients:
			if row.item == self.item:
				frappe.throw(_("Ingredients row {0}: a recipe can't use itself").format(row.idx))
			row.line_id = f"{self.item}-{row.idx:02d}"
			item = frappe.db.get_value(
				"Item", row.item, ["stock_uom", "item_group", "weight_per_unit", "weight_uom"], as_dict=True
			)
			row.stock_uom = item.stock_uom
			row.grams_per_piece = costing.grams_per_piece(item.weight_per_unit, item.weight_uom)
			try:
				costing.check_uom_compatible(row.uom, row.stock_uom, row.grams_per_piece)
			except costing.CostingError as e:
				frappe.throw(_("Ingredients row {0} ({1}): {2}").format(row.idx, row.item_name or row.item, e))
			row.basis = "per piece" if costing.STOCK_UOM_KIND.get(row.stock_uom) == "count" else "per gram"

			working = get_working_recipe(row.item)
			row.working_recipe = working.name if working else None
			if working:
				row.component_type = working.recipe_type
			elif item.item_group in packaging_groups:
				row.component_type = "Packaging"
			else:
				row.component_type = "Ingredient"

			price = None
			if working and not row.supplier:
				# made in-house: cost per yield unit of the working recipe (yield unit = stock UOM)
				row.price_source = working.recipe_type
				row.item_price = None
				row.price_per_base_unit = working.cost_per_unit
			else:
				price = costing.pick_price(get_ingredient_prices(row.item, settings.buying_price_list), row.supplier)
				row.price_source = "Supplier Price" if price else None
				row.item_price = price.item_price if price else None
				row.supplier = price.supplier if price else row.supplier
				row.price_per_base_unit = price.price_per_base_unit if price else 0
			row.price_missing = 0 if row.price_per_base_unit else 1
			self.missing_price_count += row.price_missing

	def calculate_costs(self, settings):
		line_costs = []
		self.total_input_weight = self.total_pieces_used = self.total_packaging_cost = 0
		self.total_ingredient_weight_used = 0
		for row in self.ingredients:
			try:
				line = costing.cost_line(
					row.qty, row.uom, row.yield_pct, row.price_per_base_unit, row.stock_uom, row.grams_per_piece
				)
			except costing.CostingError as e:
				frappe.throw(_("Ingredients row {0}: {1}").format(row.idx, e))
			row.base_qty = line["base_qty"]
			row.gross_qty = line["gross_qty"]
			row.line_cost = line["line_cost"]
			line_costs.append(row.line_cost)
			if row.component_type == "Packaging":
				self.total_packaging_cost += row.line_cost
				continue
			if row.basis == "per piece":
				self.total_pieces_used += row.gross_qty
			grams = costing.line_grams(row.qty, row.uom, row.grams_per_piece)
			self.total_input_weight += grams
			self.total_ingredient_weight_used += grams * 100.0 / (row.yield_pct or 100)

		for row in self.labour:
			if not row.hourly_rate:
				row.hourly_rate = settings.default_labour_rate

		try:
			s = costing.summarize(
				ingredient_costs=line_costs,
				labour=[r.as_dict() for r in self.labour],
				overheads=[r.as_dict() for r in self.overheads],
				batch_yield=self.batch_yield,
				selling_price=self.selling_price,
				target_food_cost_pct=settings.target_food_cost_pct,
			)
		except costing.CostingError as e:
			frappe.throw(str(e))

		for row, share in zip(self.ingredients, s["cost_shares"]):
			row.cost_share_pct = share
		for row, cost in zip(self.labour, s["labour_costs"]):
			row.cost = cost
		for row, amount in zip(self.overheads, s["overhead_amounts"]):
			row.amount = amount
		for field in (
			"total_ingredient_cost",
			"total_labour_cost",
			"total_labour_minutes",
			"total_overhead_cost",
			"total_batch_cost",
			"ingredient_cost_per_unit",
			"labour_cost_per_unit",
			"overhead_cost_per_unit",
			"cost_per_unit",
			"food_cost_pct",
			"total_cost_pct",
			"gross_margin",
			"suggested_price",
		):
			self.set(field, s[field])
		self.total_labour_hours = s["total_labour_minutes"] / 60
		self.total_cost_incl_labour = s["total_ingredient_cost"] + s["total_labour_cost"]
		self.cost_per_unit_incl_labour = s["ingredient_cost_per_unit"] + s["labour_cost_per_unit"]

		self.output_weight, self.cooking_yield_pct = costing.cooking_yield(
			self.total_input_weight, self.batch_yield, self.unit_weight
		)
		self.set_last_costed_on()

	COST_FIELDS = (
		"total_ingredient_cost", "total_labour_cost", "total_overhead_cost", "total_batch_cost",
		"cost_per_unit", "selling_price", "food_cost_pct", "missing_price_count",
	)

	def set_last_costed_on(self):
		"""Only move the timestamp when a cost actually changed, so the nightly
		re-costing doesn't add a 'Last Costed On changed' line to every recipe."""
		before = None if self.is_new() else self.get_doc_before_save()
		if before and before.last_costed_on and all(
			abs((before.get(f) or 0) - (self.get(f) or 0)) < 1e-6 for f in self.COST_FIELDS
		):
			self.last_costed_on = before.last_costed_on
		else:
			self.last_costed_on = now_datetime()


def recost_recipes_for_item_weight(doc, method=None):
	"""Item hook: a changed weight per piece changes gram <-> piece lines."""
	if doc.has_value_changed("weight_per_unit") or doc.has_value_changed("weight_uom"):
		if frappe.db.exists("Recipe Ingredient", {"item": doc.name, "parenttype": "Recipe"}):
			frappe.enqueue(
				"happy_kitchen.recipe_management.doctype.recipe.recipe.recost_recipes",
				item_code=doc.name,
				queue="short",
				enqueue_after_commit=True,
			)


def recost_recipes_for_item(doc, method=None):
	"""Item Price hook: re-cost the recipes that use this ingredient."""
	if not doc.buying or not frappe.db.get_single_value("Recipe Settings", "recost_on_price_change"):
		return
	frappe.enqueue(
		"happy_kitchen.recipe_management.doctype.recipe.recipe.recost_recipes",
		item_code=doc.item_code,
		queue="short",
		enqueue_after_commit=True,
	)


def recost_recipes(item_code: str | None = None, _seen: set | None = None):
	"""Re-save recipes so they pick up current prices: the ones using item_code
	(and, for working recipes, the recipes above them), or all of them."""
	seen = _seen if _seen is not None else set()
	if item_code:
		names = frappe.get_all(
			"Recipe Ingredient", filters={"item": item_code, "parenttype": "Recipe"}, pluck="parent", distinct=True
		)
	else:
		# working recipes and components first so finished products see their new cost
		names = frappe.get_all(
			"Recipe", filters={"status": ("!=", "Archived")}, pluck="name", order_by="recipe_type desc, name"
		)
	for name in names:
		if name in seen:
			continue
		seen.add(name)
		try:
			doc = frappe.get_doc("Recipe", name)
			doc.flags.ignore_permissions = True
			doc.flags.from_recost = True
			doc.save()
		except Exception:
			frappe.log_error(title=f"Re-costing recipe {name} failed")
			continue
		if item_code and doc.recipe_type in SUB_RECIPE_TYPES:
			recost_recipes(doc.item, seen)
	frappe.db.commit()
