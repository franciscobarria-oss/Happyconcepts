"""Gmail order pick-up with fake messages (no real Gmail). Rolled back."""

import base64
import time

import frappe

from happy_kitchen.hk_operations import gmail_orders

P = "E2E-MAIL-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _msg(mid, sender, subject, body, age_hours=1):
	data = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
	# an hour ago, and a copy from days ago in m2 below, so the date rules are tested whatever today is
	return {"id": mid, "internalDate": str(int((time.time() - age_hours * 3600) * 1000)), "payload": {
		"mimeType": "text/plain", "body": {"data": data},
		"headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]}}


class FakeGmail:
	def __init__(self, messages):
		self.messages = {m["id"]: m for m in messages}
		self.queries = []

	def list_ids(self, query, limit):
		self.queries.append(query)
		return list(self.messages)[:limit]

	def get_message(self, mid):
		return self.messages[mid]


def _found(txt):
	from frappe.desk.search import search_link

	return {r["value"] for r in search_link("Item", txt)}


def run():
	frappe.set_user("Administrator")
	try:
		frappe.db.set_single_value("Gmail Settings", {"label_name": "Orders", "look_back_days": 14, "default_lead_days": 2,
		                                              "max_per_run": 25, "allowed_senders": "@e2e-cafe.example"})
		existing = frappe.get_doc({
			"doctype": "Item", "item_code": P + "BROWNIE", "item_name": P + "Chocolate brownie", "stock_uom": "Nos",
			"item_group": "Products", "is_stock_item": 1, "is_sales_item": 1}).insert().name

		fake = FakeGmail([
			_msg("m1", f'"{P}Cafe" <orders@e2e-cafe.example>', "Friday order",
			     f"Hi!\nCK-001 | {P}Butter cookie | 24\n12 x {P}Chocolate brownie\n{P}Plain scone x 6\nThanks"),
			_msg("m2", f"{P}Cafe <orders@e2e-cafe.example>", "More", f"CK-001 | {P}Butter cookie | 10\nsomething | odd | line | many", age_hours=24 * 9),
			_msg("m3", "Spam <x@spam.example>", "Buy now", "100 x Pills"),
			_msg("m4", "orders@e2e-cafe.example", "Question", "Can you call me back?"),
		])
		made = gmail_orders.fetch(client=fake)
		_check('label:"Orders" newer_than:14d' in fake.queries, f"query: {fake.queries}")
		_check(made == {"new": 4, "draft": 1, "review": 2, "ignored": 1, "failed": 0}, f"summary: {made}")

		o1 = frappe.get_doc("Email Order", {"message_id": "m1"})
		_check(o1.status == "Draft order" and o1.sales_order, f"m1: {o1.status}")
		so = frappe.get_doc("Sales Order", o1.sales_order)
		_check(so.docstatus == 0, "the sales order stays a draft")
		_check({i.qty for i in so.items} == {24, 12, 6}, f"quantities: {[(i.item_code, i.qty) for i in so.items]}")
		_check(str(so.delivery_date) >= frappe.utils.nowdate(), "delivery date is never before today")
		_check(str(frappe.get_doc("Sales Order", frappe.get_doc("Email Order", {"message_id": "m2"}).sales_order).delivery_date)
		       >= frappe.utils.nowdate(), "an email picked up days late still gets a valid delivery date")

		# internal SKU (item code) + external SKU (customer's code) on the new product
		cookie = o1.lines[0]
		_check(cookie.item_created and cookie.item.startswith("SKU-"), f"new product gets an internal SKU: {cookie.item}")
		_check(frappe.db.get_value("Item Customer Detail", {"parent": cookie.item, "ref_code": "CK-001",
		                                                   "customer_name": o1.customer}, "name"), "external SKU stored on the item")
		_check(cookie.item in _found("CK-001"), "found by the customer's external SKU")
		_check(cookie.item in _found(cookie.item), "found by the internal SKU")
		# a product that already exists is reused, not duplicated
		_check(o1.lines[1].item == existing and not o1.lines[1].item_created, "existing product reused by name")
		_check(o1.lines[2].item.startswith("SKU-") and o1.lines[2].item != cookie.item, "next internal SKU")

		# same customer + same external SKU -> same product, same customer
		o2 = frappe.get_doc("Email Order", {"message_id": "m2"})
		_check(o2.customer == o1.customer and o2.lines[0].item == cookie.item and not o2.lines[0].item_created, "reused customer and product")
		_check(o2.status == "Needs review" and "many" in (o2.unparsed or ""), "unreadable line is flagged for review")
		_check(o2.sales_order, "readable lines still make a draft order")

		_check(frappe.db.get_value("Email Order", {"message_id": "m3"}, "status") == "Ignored", "other senders are ignored")
		o4 = frappe.get_doc("Email Order", {"message_id": "m4"})
		_check(o4.status == "Needs review" and not o4.sales_order, "mail with no order lines makes no sales order")

		# never picked up twice
		again = gmail_orders.fetch(client=fake)
		_check(again["new"] == 0, f"second run: {again}")
		_check(frappe.db.count("Email Order", {"message_id": ("in", ["m1", "m2", "m3", "m4"])}) == 4, "no duplicates")
		_check(frappe.db.count("Sales Order", {"customer": o1.customer}) == 2, "two draft orders")

		# scheduled run is a no-op while switched off
		gmail_orders.scheduled_fetch()
		print("ok: email orders e2e passed")
	finally:
		frappe.db.rollback()
		frappe.clear_cache()
