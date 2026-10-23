"""Gmail order pick-up with fake messages (no real Gmail). Rolled back."""

import base64
import time

import frappe

from happy_kitchen.hk_operations import gmail_orders

P = "E2E-MAIL-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _msg(mid, sender, subject, body, age_hours=1, thread=None):
	data = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
	# an hour ago, and a copy from days ago in m2 below, so the date rules are tested whatever today is
	return {"id": mid, "threadId": thread or mid, "internalDate": str(int((time.time() - age_hours * 3600) * 1000)), "payload": {
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
		                                              "max_per_run": 25, "allowed_senders": "@e2e-cafe.example", "extra_senders": ""})
		existing = frappe.get_doc({
			"doctype": "Item", "item_code": P + "BROWNIE", "item_name": P + "Chocolate brownie", "stock_uom": "Nos",
			"item_group": "Products", "is_stock_item": 1, "is_sales_item": 1}).insert().name

		fake = FakeGmail([
			_msg("m1", f'"{P}Cafe" <orders@e2e-cafe.example>', "Friday order",
			     f"Hi!\nCK-001 | {P}Butter cookie | 24\n12 x {P}Chocolate brownie\n{P}Plain scone x 6\nThanks", thread="t1"),
			_msg("m2", f"{P}Cafe <orders@e2e-cafe.example>", "More", f"CK-001 | {P}Butter cookie | 10\nsomething | odd | line | many", age_hours=24 * 9),
			_msg("m3", "Spam <x@spam.example>", "Buy now", "100 x Pills"),
			_msg("m4", "orders@e2e-cafe.example", "Question", "Can you call me back?"),
		])
		made = gmail_orders.fetch(client=fake)
		_check('label:"Orders" newer_than:14d' in fake.queries, f"query: {fake.queries}")
		_check(made == {"new": 4, "draft": 1, "revised": 0, "review": 2, "ignored": 1, "failed": 0}, f"summary: {made}")

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

		# --- revise order: a follow-up in the same thread amends the draft instead of making a second order ---
		from happy_kitchen.hk_operations import revisions_api

		fake.messages["m5"] = _msg("m5", f"{P}Cafe <orders@e2e-cafe.example>", "Re: Friday order",
		                           f"Change of plan:\nCK-001 | {P}Butter cookie | 30\n12 x {P}Chocolate brownie\n"
		                           "On Mon, 19 Oct 2026 at 10:00, Cafe wrote:\n> 24 x Cookie\n> 6 x Scone", thread="t1")
		fake.messages["m8"] = _msg("m8", f"{P}Cafe <orders@e2e-cafe.example>", "Re: Friday order",
		                           f"Just checking, still:\nCK-001 | {P}Butter cookie | 30\n12 x {P}Chocolate brownie", thread="t1")
		made = gmail_orders.fetch(client=fake)
		_check(made["new"] == 2 and made["revised"] == 1 and made["ignored"] == 1, f"follow-ups: {made}")
		o5 = frappe.get_doc("Email Order", {"message_id": "m5"})
		_check(o5.status == "Revised" and o5.sales_order == o1.sales_order and o5.revises == o1.name, f"m5: {o5.status}")
		so.reload()
		_check({i.item_code: i.qty for i in so.items} == {cookie.item: 30, existing: 12}, "the draft now has the new quantities")
		_check(so.hk_needs_review == 1 and so.hk_revision_count == 1, "revised order is flagged for review")
		_check(frappe.db.count("Sales Order", {"customer": o1.customer}) == 2, "still two orders: the follow-up made no new one")
		rev = frappe.get_doc("Order Revision", {"sales_order": so.name})
		_check(rev.source == "Email" and rev.applied and "removed" in rev.summary, f"history: {rev.summary}")
		_check(cookie.item in rev.previous_items and "24" in rev.previous_items, "earlier items are kept")
		_check(frappe.db.get_value("Email Order", {"message_id": "m8"}, "status") == "Ignored", "an email that changes nothing is ignored")

		# staff edits to an email order are kept too, then a manager marks the revision as checked
		so.items[0].qty = 31
		so.save()
		so.reload()
		_check(so.hk_revision_count == 2 and frappe.db.count("Order Revision", {"sales_order": so.name, "source": "Staff"}) == 1, "staff change recorded")
		revisions_api.mark_checked(so.name)
		_check(frappe.db.get_value("Sales Order", so.name, "hk_needs_review") == 0, "marked as checked")

		# an order that is already submitted is not changed by an email: the proposal is kept and the order flagged
		fake.messages["m6"] = _msg("m6", "Bistro <b@e2e-bistro.example>", "Order", f"BI-1 | {P}Bistro loaf | 10", thread="t2")
		frappe.db.set_single_value("Gmail Settings", "allowed_senders", "")
		gmail_orders.fetch(client=fake)
		o6 = frappe.get_doc("Email Order", {"message_id": "m6"})
		so6 = frappe.get_doc("Sales Order", o6.sales_order)
		so6.items[0].rate = 5
		so6.save()
		so6.submit()
		fake.messages["m7"] = _msg("m7", "Bistro <b@e2e-bistro.example>", "Re: Order", f"BI-1 | {P}Bistro loaf | 14", thread="t2")
		gmail_orders.fetch(client=fake)
		o7 = frappe.get_doc("Email Order", {"message_id": "m7"})
		_check(o7.status == "Needs review" and o7.sales_order == so6.name, f"m7: {o7.status}")
		so6.reload()
		_check(so6.items[0].qty == 10 and so6.hk_needs_review == 1, "the submitted order is untouched but flagged")
		proposal = frappe.get_doc("Order Revision", {"sales_order": so6.name})
		_check(not proposal.applied and "10 → 14" in proposal.summary, f"proposal kept: {proposal.summary}")

		# --- several purchase orders in one email: one draft Sales Order per PO, each with its PO no. and delivery date ---
		soon, past = frappe.utils.add_days(frappe.utils.nowdate(), 5), frappe.utils.add_days(frappe.utils.nowdate(), -3)
		body = (f"--- Attachment: orders.pdf ---\n--- PO {P}PO-1 | {soon} ---\nMP-1 | {P}Multi A | 4\nMP-2 | {P}Multi B | 6\n"
		        f"--- PO {P}PO-2 | {past} ---\nMP-3 | {P}Multi C | 8\n")
		fake.messages["m9"] = _msg("m9", "Hotel <h@e2e-hotel.example>", "Orders", body, thread="t9")
		gmail_orders.fetch(client=fake)
		o9 = frappe.get_doc("Email Order", {"message_id": "m9"})
		sos = frappe.get_all("Sales Order", filters={"po_no": ("like", f"{P}PO-%"), "customer": o9.customer},
		                     fields=["name", "po_no", "delivery_date", "docstatus"], order_by="po_no")
		_check([s.po_no for s in sos] == [f"{P}PO-1", f"{P}PO-2"] and all(s.docstatus == 0 for s in sos), f"one draft per PO: {sos}")
		_check(str(sos[0].delivery_date) == soon, f"PO-1 keeps its own delivery date: {sos[0].delivery_date}")
		_check(str(sos[1].delivery_date) >= frappe.utils.nowdate(), "a past delivery date falls back to a valid one")
		_check(len(frappe.get_doc("Sales Order", sos[0].name).items) == 2 and len(frappe.get_doc("Sales Order", sos[1].name).items) == 1,
		       "each order has only its own lines")
		_check(o9.sales_order == sos[0].name and {(l.po_no, l.sales_order) for l in o9.lines} == {(s.po_no, s.name) for s in sos},
		       "email lines point at their order")
		# a later email carrying the same PO numbers does not make more orders
		fake.messages["m10"] = _msg("m10", "Hotel <h@e2e-hotel.example>", "Orders again", body, thread="t10")
		gmail_orders.fetch(client=fake)
		_check(frappe.db.count("Sales Order", {"po_no": ("like", f"{P}PO-%"), "customer": o9.customer}) == 2, "an existing PO is skipped")
		_check(frappe.db.get_value("Email Order", {"message_id": "m10"}, "status") == "Ignored", "all POs known: ignored")

		# extra senders are searched even without the label
		frappe.db.set_single_value("Gmail Settings", "extra_senders", "e2e-plaza.example")
		gmail_orders.fetch(client=fake)
		_check('(label:"Orders" OR from:e2e-plaza.example) newer_than:14d' in fake.queries, f"extra sender query: {fake.queries[-1]}")

		# scheduled run is a no-op while switched off
		gmail_orders.scheduled_fetch()
		print("ok: email orders e2e passed")
	finally:
		frappe.db.rollback()
		frappe.clear_cache()
