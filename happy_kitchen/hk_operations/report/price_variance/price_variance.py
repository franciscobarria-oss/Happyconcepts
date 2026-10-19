# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""What we were charged against what we expected, per received line.

- List price: the supplier's price in the buying price list (Recipe Settings), per received unit.
- Last paid: the previous receipt of the same item, per received unit.
- PO price: the rate on the purchase order (stock is received at this price).
- Invoice price: what the delivery note / invoice said, typed on Receive Delivery (blank if not checked)."""

import frappe
from frappe import _
from frappe.utils import flt

from happy_kitchen.hk_operations.calc import pct_change

DEFAULT_TOLERANCE = 0.5


def execute(filters=None):
	f = frappe._dict(filters or {})
	tolerance = flt(f.tolerance) if f.tolerance not in (None, "") else DEFAULT_TOLERANCE
	price_list = frappe.db.get_single_value("Recipe Settings", "buying_price_list") or "Standard Buying"
	conditions = ["pr.docstatus = 1", "pr.posting_date between %(from_date)s and %(to_date)s"]
	if f.supplier:
		conditions.append("pr.supplier = %(supplier)s")
	if f.item_code:
		conditions.append("ri.item_code = %(item_code)s")
	lines = frappe.db.sql(
		f"""
		select pr.posting_date, pr.posting_time, pr.name as receipt, pr.supplier, pr.supplier_name,
			ri.item_code, ri.item_name, ri.uom, ri.stock_uom, ri.conversion_factor, ri.qty,
			ri.rate, ri.hk_invoice_rate as invoice_rate, ri.purchase_order
		from `tabPurchase Receipt Item` ri
		join `tabPurchase Receipt` pr on pr.name = ri.parent
		where {" and ".join(conditions)}
		order by pr.posting_date desc, pr.posting_time desc""",
		f,
		as_dict=True,
	)
	items = list({l.item_code for l in lines})
	list_prices = {}
	if items:
		for p in frappe.get_all(
			"Item Price",
			filters={"price_list": price_list, "item_code": ("in", items)},
			fields=["item_code", "supplier", "uom", "price_list_rate"],
		):
			list_prices.setdefault(p.item_code, []).append(p)

	data = []
	for l in lines:
		cf = flt(l.conversion_factor) or 1
		list_price = _list_price_per_uom(list_prices.get(l.item_code, []), l.supplier, l.uom, l.stock_uom, cf)
		last = _last_paid_per_stock_uom(l.item_code, l.posting_date, l.posting_time, l.receipt)
		last_paid = last * cf if last else None
		charged = flt(l.invoice_rate) or flt(l.rate)
		vs_list, vs_last = pct_change(charged, list_price), pct_change(charged, last_paid)
		vs_po = pct_change(l.invoice_rate, l.rate) if flt(l.invoice_rate) else None
		worst = max((abs(x) for x in (vs_list, vs_last, vs_po) if x is not None), default=0)
		if f.only_changes and worst <= tolerance:
			continue
		data.append(
			{
				**l,
				"list_price": list_price,
				"last_paid": last_paid,
				"vs_po": vs_po,
				"vs_list": vs_list,
				"vs_last": vs_last,
				"flag": worst > tolerance,
			}
		)
	return get_columns(), data


def _list_price_per_uom(prices, supplier, uom, stock_uom, cf):
	"""Supplier-specific price first, then any price for the item; converted to the received unit."""
	for p in sorted(prices, key=lambda p: 0 if p.supplier == supplier else (1 if not p.supplier else 2)):
		if p.supplier and p.supplier != supplier:
			continue
		if p.uom == uom:
			return flt(p.price_list_rate)
		if not p.uom or p.uom == stock_uom:
			return flt(p.price_list_rate) * cf
	return None


def _last_paid_per_stock_uom(item_code, posting_date, posting_time, receipt):
	row = frappe.db.sql(
		"""
		select ri.rate / nullif(ri.conversion_factor, 0)
		from `tabPurchase Receipt Item` ri join `tabPurchase Receipt` pr on pr.name = ri.parent
		where pr.docstatus = 1 and ri.item_code = %s and pr.name != %s
			and (pr.posting_date < %s or (pr.posting_date = %s and pr.posting_time < %s))
		order by pr.posting_date desc, pr.posting_time desc limit 1""",
		(item_code, receipt, posting_date, posting_date, posting_time),
	)
	return flt(row[0][0]) if row and row[0][0] else None


def get_columns():
	price = {"fieldtype": "Currency", "width": 110, "options": "currency"}
	pct = {"fieldtype": "Percent", "width": 95}
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Receipt"), "fieldname": "receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 95},
		{"label": _("Name"), "fieldname": "item_name", "width": 190},
		{"label": _("Unit"), "fieldname": "uom", "width": 65},
		{"label": _("List Price"), "fieldname": "list_price", **price},
		{"label": _("Last Paid"), "fieldname": "last_paid", **price},
		{"label": _("PO Price"), "fieldname": "rate", **price},
		{"label": _("Invoice Price"), "fieldname": "invoice_rate", **price},
		{"label": _("vs PO"), "fieldname": "vs_po", **pct},
		{"label": _("vs List"), "fieldname": "vs_list", **pct},
		{"label": _("vs Last Paid"), "fieldname": "vs_last", **pct},
		{"label": _("PO"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
	]
