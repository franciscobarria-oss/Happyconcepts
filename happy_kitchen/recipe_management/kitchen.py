"""APIs behind the kitchen screens. Production (/app/kitchen-production) for now; Wastage and
Receive Delivery join in P11.

They create the same documents as the desk forms, so every ERPNext validation, permission and
accounting rule still applies; the screens only make them quicker to fill."""

import frappe
from frappe import _
from frappe.utils import nowdate

from happy_kitchen.recipe_management import production
from happy_kitchen.recipe_management.usage import get_ingredient_usage


def _entries(entries) -> list[dict]:
	try:
		return production.clean_entries(entries)
	except ValueError:
		frappe.throw(_("Choose at least one recipe and a number of batches"))


@frappe.whitelist()
def production_recipes() -> list[dict]:
	"""Active recipes for the tiles (archived and draft recipes are left out)."""
	frappe.has_permission("Recipe Production Log", "create", throw=True)
	return frappe.get_all(
		"Recipe",
		filters={"status": production.LOGGABLE_STATUS},
		fields=["name", "recipe_name", "recipe_type", "batch_yield", "yield_uom", "image", "item_group",
		        "cost_per_unit", "total_batch_cost"],
		order_by="recipe_name",
	)


@frappe.whitelist()
def production_preview(entries) -> dict:
	"""Ingredients the run will use, with stock on hand (all storage areas)."""
	return production.preview(get_ingredient_usage(recipe_batches=_entries(entries)))


@frappe.whitelist(methods=["POST"])
def log_production(entries, posting_date=None, remarks=None) -> dict:
	"""Creates and submits a Recipe Production Log."""
	frappe.has_permission("Recipe Production Log", "create", throw=True)
	log = frappe.new_doc("Recipe Production Log")
	log.posting_date = posting_date or nowdate()
	log.remarks = remarks
	for e in _entries(entries):
		log.append("items", e)
	log.insert()
	log.submit()
	log.reload()
	return {
		"name": log.name,
		"total_cost": log.total_cost,
		"units": [(r.recipe_name, r.units) for r in log.items],
		"stock_entry": log.stock_entry,
		"batch_stock_entries": log.batch_stock_entries,
	}
