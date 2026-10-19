"""Ingredient Label Check: the fill-in sheet for product labels. Every bought-in
ingredient used in a recipe, with the name it prints under and its allergens.
Export it (Menu > Export) to fill in on paper, then enter the answers on each
Item's Label tab."""

import frappe
from frappe import _

from happy_kitchen.hk_operations import label_data as ld
from happy_kitchen.recipe_management.pricing import SUB_RECIPE_TYPES


def execute(filters=None):
	filters = frappe._dict(filters or {})
	used_in: dict[str, set] = {}
	for l in frappe.db.sql(
		"""select ri.item, ri.parent from `tabRecipe Ingredient` ri
		join `tabRecipe` r on r.name = ri.parent
		where ri.parenttype = 'Recipe' and r.status != 'Archived' and coalesce(ri.component_type, '') != 'Packaging'""",
		as_dict=True,
	):
		used_in.setdefault(l.item, set()).add(l.parent)
	made_here = set(frappe.get_all(
		"Recipe", filters={"recipe_type": ("in", SUB_RECIPE_TYPES), "status": ("!=", "Archived")}, pluck="item"
	))
	codes = list(used_in) or [""]
	items = frappe.get_all(
		"Item", filters={"name": ("in", codes), "disabled": 0},
		fields=["name", "item_name", "hk_label_name", "hk_allergens_checked"],
	)
	allergens: dict[str, list[str]] = {}
	for a in frappe.get_all("Item Allergen", filters={"parenttype": "Item", "parent": ("in", codes)},
	                        fields=["parent", "allergen"], order_by="idx asc"):
		allergens.setdefault(a.parent, []).append(a.allergen)
	rows = ld.label_check_rows(items, allergens, used_in, made_here, only_open=bool(filters.get("only_open")))
	return columns(), rows


def columns():
	return [
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "label_name", "label": _("Name in ingredient lists"), "fieldtype": "Data", "width": 200},
		{"fieldname": "prints_as", "label": _("Prints as"), "fieldtype": "Data", "width": 180},
		{"fieldname": "allergens", "label": _("Allergens"), "fieldtype": "Data", "width": 200},
		{"fieldname": "allergens_reviewed", "label": _("Allergens reviewed"), "fieldtype": "Check", "width": 90},
		{"fieldname": "recipes", "label": _("Recipes"), "fieldtype": "Int", "width": 80},
		{"fieldname": "to_do", "label": _("To do"), "fieldtype": "Data", "width": 200},
	]
