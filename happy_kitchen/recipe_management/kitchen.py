"""APIs behind the kitchen screens: Production (/app/kitchen-production), Wastage
(/app/kitchen-wastage) and Receive Delivery (/app/receive-delivery).

They create the same documents as the desk forms, so every ERPNext validation, permission and
accounting rule still applies; the screens only make them quicker to fill."""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from happy_kitchen.recipe_management import production, receiving
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


def _json(value):
	return json.loads(value) if isinstance(value, str) else (value or [])


# --------------------------------------------------------------- wastage


@frappe.whitelist()
def wastage_reasons() -> list[dict]:
	return frappe.get_all("Wastage Reason", filters={"disabled": 0}, fields=["name", "reason_zh"], order_by="creation")


@frappe.whitelist()
def find_items(txt: str = "", limit: int = 30) -> list[dict]:
	"""Stocked items (ingredients, packaging, batch preps, products) by code or name."""
	txt = (txt or "").strip()
	filters = {"is_stock_item": 1, "disabled": 0}
	or_filters = {"name": ("like", f"%{txt}%"), "item_name": ("like", f"%{txt}%")} if txt else None
	return frappe.get_all(
		"Item", filters=filters, or_filters=or_filters, fields=["name", "item_name", "stock_uom", "item_group"],
		order_by="item_name", limit=cint(limit) or 30,
	)


@frappe.whitelist(methods=["POST"])
def log_wastage(lines, posting_date=None) -> dict:
	frappe.has_permission("Wastage Log", "create", throw=True)
	lines = _json(lines)
	if not lines:
		frappe.throw(_("Add at least one item"))
	doc = frappe.new_doc("Wastage Log")
	doc.posting_date = posting_date or nowdate()
	for l in lines:
		doc.append("items", {"item": l.get("item"), "qty": flt(l.get("qty")), "uom": l.get("uom"),
		                     "reason": l.get("reason"), "notes": l.get("notes")})
	doc.insert()
	doc.submit()
	doc.reload()
	return {"name": doc.name, "total_cost": doc.total_cost, "stock_entry": doc.stock_entry, "stock_note": doc.stock_note}


# ------------------------------------------------------------- receiving


@frappe.whitelist()
def open_purchase_orders(supplier: str | None = None) -> list[dict]:
	frappe.has_permission("Purchase Receipt", "create", throw=True)
	filters = {"docstatus": 1, "per_received": ("<", 100), "status": ("not in", ["Closed", "On Hold", "Completed"])}
	if supplier:
		filters["supplier"] = supplier
	return frappe.get_all(
		"Purchase Order", filters=filters,
		fields=["name", "supplier", "supplier_name", "transaction_date", "schedule_date", "grand_total", "currency", "per_received"],
		order_by="schedule_date asc, name asc", limit=100,
	)


@frappe.whitelist()
def purchase_order_lines(po: str) -> dict:
	doc = frappe.get_doc("Purchase Order", po)
	doc.check_permission("read")
	lines = []
	from happy_kitchen.hk_operations import sku_api

	skus = sku_api.supplier_skus(doc.supplier, [i.item_code for i in doc.items])
	for i in doc.items:
		pending = flt(i.qty) - flt(i.received_qty)
		if pending <= 0:
			continue
		lines.append({"po_detail": i.name, "item": i.item_code, "item_name": i.item_name, "uom": i.uom,
		              "supplier_sku": i.get("supplier_part_no") or skus.get(i.item_code, ""),
		              "pending_qty": pending, "rate": i.rate, "warehouse": i.warehouse})
	return {"name": doc.name, "supplier": doc.supplier, "supplier_name": doc.supplier_name, "currency": doc.currency,
	        "schedule_date": str(doc.schedule_date or ""), "lines": lines}


@frappe.whitelist()
def check_delivery(lines) -> dict:
	return receiving.delivery_summary(_json(lines))


@frappe.whitelist(methods=["POST"])
def receive_po(po: str, lines, supplier_delivery_note: str | None = None, notes: str | None = None) -> dict:
	"""Purchase Receipt for the quantities that actually arrived, flagged if
	anything differs from the order. Stock is received at the ordered price
	(Buying Settings "maintain same rate"); a different invoice price is only
	flagged, to be settled on the supplier invoice."""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	frappe.has_permission("Purchase Receipt", "create", throw=True)
	given = {l["po_detail"]: l for l in _json(lines)}
	pr = make_purchase_receipt(po)
	check, keep = [], []
	for it in pr.items:
		l = given.get(it.purchase_order_item, {})
		received = flt(l.get("received_qty"))
		invoice_rate = flt(l.get("invoice_rate"))
		check.append({"item": it.item_code, "ordered_qty": flt(it.qty), "received_qty": received,
		              "po_rate": flt(it.rate), "invoice_rate": invoice_rate})
		if received <= 0:
			continue
		it.qty = it.received_qty = received
		it.rejected_qty = 0
		if invoice_rate and it.meta.has_field("hk_invoice_rate"):
			it.hk_invoice_rate = invoice_rate  # for the Price Variance report
		keep.append(it)
	if not keep:
		frappe.throw(_("Nothing was received. Enter the quantity that arrived for at least one line."))
	pr.set("items", keep)
	summary = receiving.delivery_summary(check)
	names = {c["item"]: frappe.get_cached_value("Item", c["item"], "item_name") for c in check}
	flag_text = "\n".join(f"{names[l['item']]}: {', '.join(l['flags'])}" for l in summary["lines"] if l["flags"])
	pr.hk_has_discrepancy = 1 if summary["has_discrepancy"] else 0
	pr.hk_delivery_flags = flag_text or None
	if supplier_delivery_note:
		pr.supplier_delivery_note = supplier_delivery_note
	pr.insert()
	pr.submit()
	if notes:
		pr.add_comment("Comment", notes)
	return {"name": pr.name, "grand_total": pr.grand_total, "flags": flag_text, "has_discrepancy": summary["has_discrepancy"]}
