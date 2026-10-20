"""Order revisions: who changed what on an order, and "check before delivering".

A change to an order's items or quantities is a revision when the order came from an email or
has been submitted. Each one is kept in Order Revision (items before and after) and flags the
Sales Order until a manager marks it checked. Rules in revisions.py."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from happy_kitchen.hk_operations import revisions

MANAGER_ROLES = ("System Manager", "Sales Manager")


def lines(items) -> list[dict]:
	return [{"item_code": i.item_code, "qty": i.qty} for i in items or []]


def names(codes) -> dict:
	rows = frappe.get_all("Item", filters={"name": ("in", list(codes) or [""])}, fields=["name", "item_name"])
	return {r.name: r.item_name for r in rows}


def record(sales_order: str, before, after, source: str, applied: int = 1, email_order: str | None = None):
	"""Write the Order Revision for before -> after; None when nothing changed."""
	diff = revisions.changes(before, after)
	if not diff:
		return None
	rev = frappe.get_doc({
		"doctype": "Order Revision", "sales_order": sales_order, "source": source, "applied": applied,
		"revised_on": now_datetime(), "revised_by": frappe.session.user, "email_order": email_order,
		"summary": revisions.summary(diff, names(c for c, _a, _b in diff)),
		"previous_items": json.dumps(sorted(revisions.normalize(before).items())),
		"proposed_items": json.dumps(sorted(revisions.normalize(after).items())),
	}).insert(ignore_permissions=True)
	return rev


def track(doc, method=None):
	"""Sales Order validate / before_update_after_submit: keep a revision for item changes."""
	if doc.is_new():
		return
	before = doc.get_doc_before_save()
	if before is None or not (doc.docstatus == 1 or doc.get("hk_email_order")):
		return
	rev = record(doc.name, lines(before.items), lines(doc.items), doc.flags.get("hk_revision_source") or "Staff",
	             email_order=doc.flags.get("hk_revision_email_order") or doc.get("hk_email_order"))
	if rev:
		doc.hk_revision_count = int(before.get("hk_revision_count") or 0) + 1
		doc.hk_needs_review = 1


def flag_proposal(sales_order: str, rev):
	"""A follow-up email for an order that is already submitted: the order is not changed, it is
	flagged and the proposal is kept for a person to apply."""
	frappe.db.set_value("Sales Order", sales_order, "hk_needs_review", 1, update_modified=False)
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Sales Order",
	                "reference_name": sales_order,
	                "content": _("A newer email proposes changes to this submitted order ({0}): {1}").format(rev.name, rev.summary)}
	               ).insert(ignore_permissions=True)


@frappe.whitelist()
def mark_checked(sales_order: str) -> None:
	frappe.only_for(MANAGER_ROLES)
	frappe.db.set_value("Sales Order", sales_order, "hk_needs_review", 0, update_modified=False)
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Sales Order",
	                "reference_name": sales_order,
	                "content": _("Revision checked by {0}.").format(frappe.get_fullname())}).insert(ignore_permissions=True)
