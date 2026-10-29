""""Complete" on a confirmed Sales Order. Rules in order_stage.py.

Recipe Settings `complete_with_delivery_note` on: one Delivery Note for what is left, submitted in
the same request (all or nothing; needs the stock to be there). Off (the default while stock isn't
counted): the order is closed (ERPNext's own Close, re-open from Status) and moves no stock."""

import frappe
from frappe import _

from happy_kitchen.hk_operations import order_stage


def _with_delivery_note() -> bool:
	return bool(frappe.db.get_single_value("Recipe Settings", "complete_with_delivery_note"))


@frappe.whitelist(methods=["POST"])
def mark_delivered(sales_order: str) -> dict:
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("write")
	why = order_stage.deliver_blocker(so.docstatus, so.status, so.per_delivered, so.get("hk_needs_review"))
	if why:
		frappe.throw(_(why))

	if not _with_delivery_note():
		so.update_status("Closed")
		so.add_comment("Info", _("Completed by {0} without a delivery note (stock is not tracked yet).").format(
			frappe.utils.get_fullname(frappe.session.user)))
		return {"delivery_note": None}

	if not frappe.has_permission("Delivery Note", "submit"):
		frappe.throw(_("You are not allowed to submit a Delivery Note."), frappe.PermissionError)
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	if not dn.get("items"):
		frappe.throw(_("Nothing is left to deliver on this order."))
	dn.insert()
	dn.submit()
	return {"delivery_note": dn.name}
