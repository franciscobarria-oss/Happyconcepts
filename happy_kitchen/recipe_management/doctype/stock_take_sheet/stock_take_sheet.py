# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""The editable list of ingredients that a stock take counts: which items,
in which storage area, in what order and in what unit. Inactive rows stay on
the sheet but are not counted."""

import frappe
from frappe import _
from frappe.model.document import Document

from happy_kitchen.recipe_management.variance import compact_packs, default_count_uom, suggest_packs

PACK_UOM_FIELDS = ("pack_uom", "pack_uom_2", "pack_uom_3")

# Item groups offered by "Add all stocked ingredients" (with their sub-groups)
STOCK_TAKE_ITEM_GROUPS = ("Raw Material", "Batch Preparations")


class StockTakeSheet(Document):
	def before_validate(self):
		self.company = self.company or default_company()

	def validate(self):
		seen = set()
		for row in self.items:
			if not row.storage_area:
				row.storage_area = item_default_warehouse(row.item, self.company)
			if not row.storage_area:
				frappe.throw(_("Row {0} ({1}): set a storage area").format(row.idx, row.item))
			key = (row.item, row.storage_area)
			if key in seen:
				frappe.throw(_("Row {0}: {1} is already on the sheet for {2}").format(row.idx, row.item, row.storage_area))
			seen.add(key)
			if not row.count_uom:
				row.count_uom = default_count_uom(frappe.get_cached_value("Item", row.item, "stock_uom"))
			# pack sizes fill from the left: "Pack Size 3" alone becomes Pack Size 1
			packs = compact_packs(row.get(f) for f in PACK_UOM_FIELDS)
			for f, uom in zip(PACK_UOM_FIELDS, packs + [None] * len(PACK_UOM_FIELDS)):
				row.set(f, uom)
			for uom in packs:
				if not frappe.db.exists("UOM Conversion Detail", {"parent": row.item, "uom": uom}):
					frappe.throw(
						_("Row {0} ({1}): add {2} to the Item's Units of Measure (with how many {3} it holds) before counting in it").format(
							row.idx, row.item_name or row.item, uom, frappe.get_cached_value("Item", row.item, "stock_uom")
						)
					)
		self.active_rows = sum(1 for r in self.items if r.active)


def default_company() -> str | None:
	return frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")


def item_default_warehouse(item_code: str, company: str) -> str | None:
	return frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")


def stocked_ingredients(company: str) -> list[dict]:
	"""Enabled stock items in the ingredient, packaging and batch-preparation
	groups, ordered by storage area then name."""
	groups = set()
	for g in STOCK_TAKE_ITEM_GROUPS:
		if frappe.db.exists("Item Group", g):
			lft, rgt = frappe.db.get_value("Item Group", g, ["lft", "rgt"])
			groups.update(frappe.get_all("Item Group", filters={"lft": (">=", lft), "rgt": ("<=", rgt)}, pluck="name"))
	items = frappe.get_all(
		"Item",
		filters={"is_stock_item": 1, "disabled": 0, "item_group": ("in", list(groups))},
		fields=["name", "item_name", "stock_uom"],
	)
	order = {"Fridge": 0, "Freezer": 1, "Dry Stock": 2}
	rows = []
	for it in items:
		wh = item_default_warehouse(it.name, company)
		rows.append({"item": it.name, "item_name": it.item_name, "storage_area": wh, "count_uom": default_count_uom(it.stock_uom), "active": 1})
	rows.sort(key=lambda r: (order.get((r["storage_area"] or "").split(" - ")[0], 9), r["storage_area"] or "", (r["item_name"] or "").lower()))
	return rows


@frappe.whitelist()
def add_stocked_ingredients(sheet: str) -> int:
	"""Append every stocked ingredient that isn't on the sheet yet."""
	doc = frappe.get_doc("Stock Take Sheet", sheet)
	doc.check_permission("write")
	have = {(r.item, r.storage_area) for r in doc.items}
	added = 0
	for row in stocked_ingredients(doc.company):
		if (row["item"], row["storage_area"]) not in have and row["storage_area"]:
			doc.append("items", row)
			added += 1
	doc.save()
	return added


def item_pack_sizes(item_code: str) -> list[str]:
	"""Up to three pack sizes from the Item's UOM conversions, biggest first."""
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	conversions = frappe.get_all(
		"UOM Conversion Detail", filters={"parent": item_code, "parenttype": "Item"}, fields=["uom", "conversion_factor"]
	)
	return suggest_packs([(c.uom, c.conversion_factor) for c in conversions], stock_uom)


@frappe.whitelist(methods=["POST"])
def fill_pack_sizes(sheet: str, overwrite: int = 0) -> dict:
	"""Set each row's pack sizes from its Item. Rows that already have pack
	sizes are left alone unless overwrite is set."""
	doc = frappe.get_doc("Stock Take Sheet", sheet)
	doc.check_permission("write")
	filled = unchanged = 0
	for row in doc.items:
		have = [row.get(f) for f in PACK_UOM_FIELDS if row.get(f)]
		if have and not int(overwrite):
			continue
		packs = item_pack_sizes(row.item)
		if packs == have or not packs:
			unchanged += 1
			continue
		for f, uom in zip(PACK_UOM_FIELDS, packs + [None] * len(PACK_UOM_FIELDS)):
			row.set(f, uom)
		filled += 1
	doc.save()
	missing = sum(1 for r in doc.items if r.active and not r.pack_uom)
	return {"filled": filled, "no_packs": missing}
