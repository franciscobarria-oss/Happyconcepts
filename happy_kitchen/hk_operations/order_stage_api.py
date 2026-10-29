""""Mark as delivered" on a confirmed Sales Order: one Delivery Note for what is left, submitted
in the same request (all or nothing). Rules in order_stage.py."""

import frappe
from frappe import _

from happy_kitchen.hk_operations import order_stage


@frappe.whitelist(methods=["POST"])
def mark_delivered(sales_order: str) -> str:
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	why = order_stage.deliver_blocker(so.docstatus, so.status, so.per_delivered, so.get("hk_needs_review"))
	if why:
		frappe.throw(_(why).format(_(so.status)))
	if not frappe.has_permission("Delivery Note", "submit"):
		frappe.throw(_("You are not allowed to submit a Delivery Note."), frappe.PermissionError)

	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	if not dn.get("items"):
		frappe.throw(_("Nothing is left to deliver on this order."))
	dn.insert()
	dn.submit()
	return dn.name
