"""Data for the "HK Sales" block on the Selling workspace. Maths in sales_stats.py.

Units come from Sales Order lines (stock quantity in the stock unit), dated by the line's
delivery date (falling back to the order's). Cancelled orders never count; drafts count only
when asked, and the reply always says how many drafts the range holds."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from happy_kitchen.hk_operations import sales_stats

DEFAULT_DAYS = 84  # 12 weeks


@frappe.whitelist()
def sales(from_date=None, to_date=None, include_drafts=0, item_code=None, all=0) -> dict:
	"""`all` = from the first order on record (from_date is ignored)."""
	frappe.has_permission("Sales Order", "read", throw=True)
	bounds = frappe.db.sql(
		"""select min(coalesce(delivery_date, transaction_date)), max(coalesce(delivery_date, transaction_date))
		from `tabSales Order` where docstatus < 2"""
	)[0]
	to_date = getdate(to_date or today())
	if frappe.utils.cint(all) and bounds[0]:
		from_date = bounds[0]
		to_date = max(to_date, getdate(bounds[1]))
	from_date = getdate(from_date or add_days(to_date, -DEFAULT_DAYS + 1))
	if from_date > to_date:
		frappe.throw(_("The start date is after the end date."))
	include_drafts = frappe.utils.cint(include_drafts)
	docstatus = (0, 1) if include_drafts else (1,)

	day = "coalesce(soi.delivery_date, so.delivery_date, so.transaction_date)"
	where = f"so.docstatus in %(docstatus)s and {day} between %(from)s and %(to)s"
	args = {"docstatus": docstatus, "from": from_date, "to": to_date}
	if item_code:
		where += " and soi.item_code = %(item)s"
		args["item"] = item_code
	lines = frappe.db.sql(
		f"""select {day} as date, soi.item_code, soi.item_name, soi.stock_uom as uom,
			coalesce(nullif(soi.stock_qty, 0), soi.qty) as qty, soi.base_net_amount as amount, so.name as `order`
		from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		where {where}""",
		args,
		as_dict=True,
	)
	data = sales_stats.summarise(lines, from_date, to_date)

	counts = frappe.db.sql(
		"""select docstatus, count(*) from `tabSales Order`
		where docstatus < 2 and coalesce(delivery_date, transaction_date) between %s and %s
		group by docstatus""",
		(from_date, to_date),
	)
	counts = dict(counts)
	data.update({
		"from_date": str(from_date),
		"to_date": str(to_date),
		"include_drafts": include_drafts,
		"item_code": item_code or None,
		"item_name": frappe.db.get_value("Item", item_code, "item_name") if item_code else None,
		"submitted_orders": counts.get(1, 0),
		"draft_orders": counts.get(0, 0),
		"first_date": str(bounds[0]) if bounds[0] else None,
		"last_date": str(bounds[1]) if bounds[1] else None,
		"currency": frappe.db.get_default("currency"),
	})
	return data
