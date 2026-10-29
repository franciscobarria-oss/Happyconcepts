# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from happy_kitchen.recipe_management.pricing import get_settings
from happy_kitchen.recipe_management.production import BATCH_PREPARATION, LOGGABLE_STATUS, split_runs, stock_qty
from happy_kitchen.recipe_management.usage import get_ingredient_usage


class RecipeProductionLog(Document):
	def validate(self):
		if not self.warehouse:
			self.warehouse = get_settings().default_warehouse
		self.total_cost = 0
		for row in self.items:
			if flt(row.batches) <= 0:
				frappe.throw(_("Row {0}: batches must be more than 0").format(row.idx))
			recipe = frappe.db.get_value(
				"Recipe", row.recipe, ["batch_yield", "total_batch_cost", "status"], as_dict=True
			)
			if recipe.status != LOGGABLE_STATUS:
				frappe.throw(
					_("Row {0}: recipe {1} is {2}. Only Active recipes can be produced.").format(
						row.idx, row.recipe, _(recipe.status or "Draft")
					)
				)
			row.units = flt(row.batches) * flt(recipe.batch_yield)
			row.batch_cost = recipe.total_batch_cost
			row.amount = flt(row.batches) * flt(recipe.total_batch_cost)
			self.total_cost += row.amount

	def on_submit(self):
		from happy_kitchen.hk_operations import dates_api

		dates_api.assign_batches(self)
		if get_settings().create_stock_entry_on_submit:
			make_batch_preparation_entries(self.name)
			make_stock_entry(self.name)
		dates_api.queue_batch_labels_on_submit(self)


def _check_log(name: str):
	log = frappe.get_doc("Recipe Production Log", name)
	log.check_permission("read")
	frappe.has_permission("Stock Entry", "create", throw=True)
	if log.docstatus != 1:
		frappe.throw(_("Submit the Production Log first"))
	if not log.warehouse:
		frappe.throw(_("Set a warehouse on the Production Log (or a default in Recipe Settings)"))
	return log


def _recipe_types(log) -> dict[str, str]:
	names = list({r.recipe for r in log.items})
	return dict(frappe.get_all("Recipe", filters={"name": ("in", names)}, fields=["name", "recipe_type"], as_list=True))


def _item_warehouse(item_code: str, company: str, fallback: str) -> str:
	"""The item's default warehouse for the company (Dry Stock, Fridge or Freezer); the log's
	warehouse is the fallback."""
	return (
		frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")
		or fallback
	)


def _qty(qty, uom: str) -> float:
	return stock_qty(qty, bool(frappe.get_cached_value("UOM", uom, "must_be_whole_number")))


def _new_entry(log, purpose: str, company: str, remarks: str):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = purpose
	se.purpose = purpose
	se.company = company
	se.posting_date = log.posting_date
	se.set_posting_time = 1
	se.remarks = remarks
	return se


def _append_ingredients(se, runs, company: str, fallback: str):
	for u in get_ingredient_usage(recipe_batches=runs):
		if flt(u["gross_qty"]) <= 0:
			continue
		se.append(
			"items",
			{
				"item_code": u["item"],
				"qty": _qty(u["gross_qty"], u["stock_uom"]),
				"uom": u["stock_uom"],
				"stock_uom": u["stock_uom"],
				"conversion_factor": 1,
				"s_warehouse": _item_warehouse(u["item"], company, fallback),
			},
		)


@frappe.whitelist()
def make_stock_entry(name: str) -> str | None:
	"""Draft Material Issue for the gross ingredient quantities of the log's recipes, except
	batch preparations (their ingredients go through their own Manufacture entries)."""
	log = _check_log(name)
	if log.stock_entry and frappe.db.exists("Stock Entry", {"name": log.stock_entry, "docstatus": ("<", 2)}):
		return log.stock_entry

	_batch, other = split_runs([{"recipe": r.recipe, "batches": r.batches} for r in log.items], _recipe_types(log))
	if not other:
		return None
	company = frappe.db.get_value("Warehouse", log.warehouse, "company")
	se = _new_entry(log, "Material Issue", company, _("Ingredient usage from Recipe Production Log {0}").format(log.name))
	_append_ingredients(se, other, company, log.warehouse)
	if not se.items:
		return None
	se.insert()
	log.db_set("stock_entry", se.name)
	return se.name


@frappe.whitelist()
def make_batch_preparation_entries(name: str) -> list[str]:
	"""One draft Manufacture entry per batch-preparation row: the recipe's ingredients leave
	stock and the produced units go to the item's warehouse (e.g. Freezer), valued at the cost
	of the ingredients used (labour and overheads are not stock value)."""
	log = _check_log(name)
	existing = [
		n for n in (log.batch_stock_entries or "").split()
		if frappe.db.exists("Stock Entry", {"name": n, "docstatus": ("<", 2)})
	]
	if existing:
		return existing

	company = frappe.db.get_value("Warehouse", log.warehouse, "company")
	types = _recipe_types(log)
	created = []
	for row in log.items:
		if types.get(row.recipe) != BATCH_PREPARATION:
			continue
		recipe = frappe.db.get_value("Recipe", row.recipe, ["item", "yield_uom"], as_dict=True)
		stock_uom = frappe.db.get_value("Item", recipe.item, "stock_uom")
		if recipe.yield_uom and recipe.yield_uom != stock_uom:
			frappe.throw(
				_("Row {0}: recipe {1} yields {2} but item {3} is stocked in {4}. Make them the same.").format(
					row.idx, row.recipe, recipe.yield_uom, recipe.item, stock_uom
				)
			)
		se = _new_entry(
			log, "Manufacture", company,
			_("Batch preparation {0} x {1} from Recipe Production Log {2}").format(row.recipe, flt(row.batches), log.name),
		)
		se.fg_completed_qty = flt(row.units)
		_append_ingredients(se, [{"recipe": row.recipe, "batches": row.batches}], company, log.warehouse)
		finished = {
			"item_code": recipe.item,
			"qty": flt(row.units),
			"uom": stock_uom,
			"stock_uom": stock_uom,
			"conversion_factor": 1,
			"t_warehouse": _item_warehouse(recipe.item, company, log.warehouse),
			"is_finished_item": 1,
		}
		if row.batch_no:  # only set when the item already tracks batches
			finished.update({"use_serial_batch_fields": 1, "batch_no": row.batch_no})
		se.append("items", finished)
		se.insert()
		created.append(se.name)
	if created:
		log.db_set("batch_stock_entries", "\n".join(created))
	return created
