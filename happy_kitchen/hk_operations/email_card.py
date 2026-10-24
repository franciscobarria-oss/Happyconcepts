"""Data for the "Email orders" card on the Today page (one call from today.today)."""

import frappe
from frappe.utils import add_days, get_datetime, nowdate, time_diff_in_seconds, now_datetime

from happy_kitchen.hk_operations import email_card_rules as rules

REVIEW = ["Needs review", "Failed"]


def card() -> dict | None:
	"""Counts and pick-up health for people who can read Email Orders, else None."""
	if not (frappe.db.exists("DocType", "Email Order") and frappe.has_permission("Email Order", "read")):
		return None
	today = nowdate()
	review = frappe.get_all("Email Order", filters={"status": ("in", REVIEW), "sales_order": ("is", "not set")}, pluck="name")
	with_pdf = 0
	if review:
		with_pdf = len(set(frappe.get_all("File", filters={"attached_to_doctype": "Email Order", "attached_to_name": ("in", review)},
		                                  pluck="attached_to_name")))
	drafts = []
	if frappe.get_meta("Sales Order").has_field("hk_email_order") and frappe.has_permission("Sales Order", "read"):
		drafts = frappe.get_all("Sales Order", filters={"docstatus": 0, "hk_email_order": ("is", "set")}, pluck="delivery_date")
	new_mail = frappe.db.count("Email Order", {"creation": (">=", add_days(today, -1))})

	s = frappe.get_single("Gmail Settings")
	minutes = None
	if s.last_checked:
		minutes = time_diff_in_seconds(now_datetime(), get_datetime(s.last_checked)) / 60
	complete = bool(s.client_id and s.get_password("client_secret", raise_exception=False)
	                and s.get_password("refresh_token", raise_exception=False))
	tone, message = rules.pickup_health(bool(s.enabled), complete, s.last_error, minutes)
	can_admin = "System Manager" in frappe.get_roles()
	return {
		"review": len(review), "review_with_pdf": with_pdf, "drafts": len(drafts), "new_mail": new_mail,
		"buckets": rules.delivery_buckets([str(d) if d else "" for d in drafts], today),
		"health": {"tone": tone, "message": message, "last_checked": str(s.last_checked or ""), "error": (s.last_error or "")[:200],
		           "label": s.label_name, "extra_senders": (s.extra_senders or "").strip()},
		"can_admin": can_admin,
	}
