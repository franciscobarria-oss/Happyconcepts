"""Supplier "Products" tab, "+ Add Product" and the MOQ checks on Purchase Orders (server side).
The maths is in moq.py; this module only reads and writes documents."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from happy_kitchen.hk_operations import moq

BUYING_PRICE_LIST = "Standard Buying"


# --- Purchase Order hooks (doc_events) -------------------------------------------------------

def _order_errors(doc):
	totals = moq.total_stock_qty([d.as_dict() for d in doc.get("items") or []])
	if not totals:
		return []
	items = {
		r.name: r
		for r in frappe.get_all(
			"Item", filters={"name": ["in", list(totals)]},
			fields=["name", "item_name", "stock_uom", "hk_order_multiple"],
		)
	}
	return moq.multiple_errors(totals, items)


def _multiple_message(e):
	try_qty = f"{e['lower']:g} or {e['upper']:g}" if e["lower"] else f"{e['upper']:g}"
	return _("{0} ({1}) is sold in multiples of {2} {3}. You ordered {4}; try {5}.").format(
		e["item_code"], frappe.utils.escape_html(e["item_name"]), f"{e['multiple']:g}", e["stock_uom"],
		f"{e['qty']:g}", try_qty,
	)


def _shortfall(doc):
	if not doc.supplier:
		return 0, 0
	minimum = flt(frappe.db.get_value("Supplier", doc.supplier, "hk_min_order_amount"))
	return moq.minimum_shortfall(doc.base_net_total, minimum), minimum


def validate_purchase_order(doc, method=None):
	errors = _order_errors(doc)
	if errors:
		frappe.throw("<br>".join(_multiple_message(e) for e in errors), title=_("Order quantity not allowed"))


def before_submit_purchase_order(doc, method=None):
	gap, minimum = _shortfall(doc)
	if gap:
		cur = frappe.get_cached_value("Company", doc.company, "default_currency")
		frappe.throw(
			_("{0} requires a minimum order of {1}. This order is {2}, so {3} more is needed.").format(
				doc.supplier, fmt_money(minimum, currency=cur), fmt_money(doc.base_net_total, currency=cur),
				fmt_money(gap, currency=cur),
			),
			title=_("Minimum order not reached"),
		)


# --- Supplier Products tab -------------------------------------------------------------------

@frappe.whitelist()
def get_supplier_products(supplier):
	frappe.has_permission("Supplier", "read", supplier, throw=True)
	codes = frappe.get_all("Item Supplier", filters={"supplier": supplier, "parenttype": "Item"}, pluck="parent")
	items = frappe.get_all(
		"Item", filters={"name": ["in", codes or [""]]},
		fields=["name", "item_name", "item_group", "stock_uom", "disabled", "min_order_qty", "hk_order_multiple"],
		order_by="item_name asc",
	)
	prices = {}
	for p in frappe.get_all(
		"Item Price", filters={"supplier": supplier, "buying": 1, "item_code": ["in", codes or [""]]},
		fields=["item_code", "price_list_rate", "uom", "price_list"],
		order_by="price_list_rate asc",
	):
		# prefer the Standard Buying price when a supplier has several lists
		if p.item_code not in prices or p.price_list == BUYING_PRICE_LIST:
			prices[p.item_code] = p
	for it in items:
		it["price"] = prices.get(it.name)
	return items


@frappe.whitelist()
def add_supplier_product(supplier, item_name, price, uom, item_group, min_order_qty=0, order_multiple=0,
                         link_existing=0):
	"""Create (or, with link_existing=1, link) an ING-xxx item bought from `supplier` with its
	Standard Buying price. Returns {"item_code", "created"} or {"exists": {...}} asking the user to confirm."""
	frappe.has_permission("Item", "create", throw=True)
	frappe.has_permission("Item Price", "create", throw=True)
	frappe.has_permission("Supplier", "read", supplier, throw=True)
	name = (item_name or "").strip()
	if not name:
		frappe.throw(_("Name is required."))
	if flt(price) <= 0:
		frappe.throw(_("Price must be greater than zero."))
	stock_uom, rate, (min_qty, multiple) = moq.to_stock_units(flt(price), uom, (min_order_qty, order_multiple))

	existing = frappe.db.get_value("Item", {"item_name": name}, ["name", "stock_uom"], as_dict=True)
	if existing:
		if existing.stock_uom != stock_uom:
			frappe.throw(_("{0} already exists as {1} and is measured in {2}. Choose {2} as the UOM.").format(
				name, existing.name, existing.stock_uom))
		if not int(link_existing):
			return {"exists": {"item_code": existing.name, "item_name": name}}
		if frappe.db.exists("Item Price", {"item_code": existing.name, "supplier": supplier,
		                                   "price_list": BUYING_PRICE_LIST}):
			frappe.throw(_("{0} already has a price from {1}. Edit it on the Item Price list instead.").format(
				existing.name, supplier))
		item = frappe.get_doc("Item", existing.name)
		if not any(r.supplier == supplier for r in item.supplier_items):
			item.append("supplier_items", {"supplier": supplier})
			item.save()
		code, created = item.name, False
	else:
		existing_codes = frappe.get_all("Item", filters={"name": ["like", "ING-%"]}, pluck="name")
		company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		item = frappe.get_doc({
			"doctype": "Item",
			"item_code": moq.next_item_code(existing_codes),
			"item_name": name,
			"item_group": item_group,
			"stock_uom": stock_uom,
			"is_stock_item": 1,
			"is_purchase_item": 1,
			"is_sales_item": 0,
			"min_order_qty": min_qty,
			"hk_order_multiple": multiple,
			"supplier_items": [{"supplier": supplier}],
			"item_defaults": [{"company": company, "default_supplier": supplier}] if company else [],
		}).insert()
		code, created = item.name, True

	# one transaction: if the price fails, the new item is rolled back with it
	frappe.get_doc({
		"doctype": "Item Price", "item_code": code, "price_list": BUYING_PRICE_LIST,
		"uom": stock_uom, "price_list_rate": rate, "supplier": supplier,
	}).insert()
	return {"item_code": code, "created": created}
