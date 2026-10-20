"""Pick up orders from Gmail (read-only) and turn them into draft Sales Orders.

Safe by design: the only Google scope is gmail.readonly (nothing is sent, labelled or
deleted); only mail under one Gmail label (and, if set, from the listed senders) is read;
each message becomes one Email Order keyed by its Gmail message id, so it is never
picked up twice; the Sales Order stays a draft for a person to review. Rules for reading
the text are in email_orders.py (pure, tested). Secrets live in Gmail Settings
(Password fields); they are never logged or returned."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from happy_kitchen.hk_operations import email_orders, revisions_api, sku

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
PRODUCT_GROUP = "Products"
CODE_PREFIX = "SKU-"
TIMEOUT = 30


class GmailClient:
	"""Minimal read-only Gmail REST client (users.messages.list / get, users.getProfile)."""

	def __init__(self, settings):
		self.client_id = settings.client_id
		self.client_secret = settings.get_password("client_secret", raise_exception=False)
		self.refresh_token = settings.get_password("refresh_token", raise_exception=False)
		self._token = None

	def _headers(self):
		import requests

		if not self._token:
			missing = [label for label, v in (("client ID", self.client_id), ("client secret", self.client_secret),
			                                  ("refresh token", self.refresh_token)) if not v]
			if missing:
				frappe.throw(_("Gmail Settings is missing: {0}.").format(", ".join(missing)))
			r = requests.post(
				GOOGLE_TOKEN_URL,
				data={"client_id": self.client_id, "client_secret": self.client_secret,
				      "refresh_token": self.refresh_token, "grant_type": "refresh_token"},
				timeout=TIMEOUT,
			)
			if r.status_code != 200:
				# the response can echo request details: report only Google's error code
				body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
				code = body.get("error", r.status_code)
				if body.get("error_description"):
					code = f"{code}: {body['error_description']}"
				frappe.throw(_("Google refused the sign-in ({0}). Run the Google sign-in step again.").format(code))
			self._token = r.json()["access_token"]
		return {"Authorization": f"Bearer {self._token}"}

	def _get(self, path, **params):
		import requests

		r = requests.get(f"{GMAIL_API}/{path}", headers=self._headers(), params=params, timeout=TIMEOUT)
		if r.status_code != 200:
			try:
				err = r.json().get("error") or {}
				why = err.get("status") or ""
				if err.get("message"):
					why = f"{why}: {err['message']}" if why else err["message"]
			except Exception:
				why = ""
			frappe.throw(_("Gmail answered {0}.").format(f"{r.status_code} ({why})" if why else r.status_code))
		return r.json()

	def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
		import base64

		data = self._get(f"messages/{message_id}/attachments/{attachment_id}").get("data") or ""
		return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

	def profile(self) -> str:
		return self._get("profile").get("emailAddress") or ""

	def list_ids(self, query: str, limit: int) -> list[str]:
		out, token = [], None
		while len(out) < limit:
			data = self._get("messages", q=query, maxResults=min(100, limit - len(out)),
			                 **({"pageToken": token} if token else {}))
			out += [m["id"] for m in data.get("messages") or []]
			token = data.get("nextPageToken")
			if not token:
				break
		return out[:limit]

	def get_message(self, message_id: str) -> dict:
		return self._get(f"messages/{message_id}", format="full")


def build_query(label: str, look_back_days: int) -> str:
	label = (label or "").replace('"', "").strip()
	return f'label:"{label}" newer_than:{int(look_back_days or 14)}d'


# --- pick-up ----------------------------------------------------------------------------

def fetch(client=None) -> dict:
	"""Read new mail under the label and make an Email Order (and a draft Sales Order) for each.
	`client` is injected by the tests; otherwise the real Gmail client."""
	s = frappe.get_single("Gmail Settings")
	if client is None:
		if not (s.client_id and s.get_password("client_secret", raise_exception=False)
		        and s.get_password("refresh_token", raise_exception=False)):
			frappe.throw(_("Gmail Settings needs the Google client ID, secret and refresh token first."))
		client = GmailClient(s)
	made = {"new": 0, "draft": 0, "revised": 0, "review": 0, "ignored": 0, "failed": 0}
	try:
		ids = client.list_ids(build_query(s.label_name, s.look_back_days), int(s.max_per_run or 25))
		known = set(frappe.get_all("Email Order", filters={"message_id": ("in", ids or [""])}, pluck="message_id"))
		for mid in ids:
			if mid in known:
				continue
			made["new"] += 1
			status = _take(client, mid, s)
			made[{"Draft order": "draft", "Revised": "revised", "Needs review": "review", "Ignored": "ignored"}.get(status, "failed")] += 1
		frappe.db.set_single_value("Gmail Settings", "last_error", "")
	except Exception as e:
		frappe.db.set_single_value("Gmail Settings", "last_error", str(e)[:500])
		raise
	finally:
		frappe.db.set_single_value("Gmail Settings", "last_checked", now_datetime())
	return made


def _take(client, message_id: str, s) -> str:
	"""One message -> one Email Order. A failure on one message never stops the others."""
	payload_msg = client.get_message(message_id)
	payload = payload_msg.get("payload") or {}
	name, address = email_orders.parse_sender(email_orders.header(payload, "From"))
	order = frappe.get_doc({
		"doctype": "Email Order", "message_id": message_id, "status": "New",
		"subject": (email_orders.header(payload, "Subject") or _("(no subject)"))[:140],
		"sender_name": name, "sender_email": address,
		"received_on": _received(payload_msg), "thread_id": payload_msg.get("threadId"),
	})
	if not email_orders.sender_allowed(address, s.allowed_senders):
		order.status = "Ignored"
		order.insert(ignore_permissions=True)
		return order.status
	files = _pdf_files(client, message_id, payload)
	order.body = email_orders.join_attachment_text(
		email_orders.body_text(payload), [(n, pdf_text(raw)) for n, raw in files])
	order.insert(ignore_permissions=True)
	_save_files(order, files)
	point = f"hk_email_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(point)
	try:
		process(order, lead_days=int(s.default_lead_days or 1), prior=find_prior(order))
	except Exception:
		frappe.db.rollback(save_point=point)
		order.reload()
		order.status = "Failed"
		order.error = frappe.get_traceback(with_context=False)[-500:]
		order.save(ignore_permissions=True)
	return order.status


def _pdf_files(client, message_id: str, payload: dict) -> list[tuple[str, bytes]]:
	"""(file name, bytes) of each PDF attached to the message; one that cannot be fetched is skipped."""
	import base64

	out = []
	for att in email_orders.pdf_attachments(payload):
		try:
			if att.get("data"):
				data = att["data"]
				raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
			else:
				raw = client.get_attachment(message_id, att["attachment_id"])
			out.append((att["filename"], raw))
		except Exception:
			continue
	return out


def pdf_text(raw: bytes) -> str:
	"""What the order reader gets from a PDF: the lines of its tables when it has a table with a
	quantity column, else its page text. Needs no network; a scanned PDF has no text (no OCR)."""
	import io

	import pdfplumber

	rows = []
	try:
		with pdfplumber.open(io.BytesIO(raw)) as pdf:
			for page in pdf.pages[:10]:
				for table in page.extract_tables() or []:
					rows += table
	except Exception:
		rows = []
	lines = email_orders.drop_repeats(email_orders.table_to_lines(rows))
	if lines:
		return "\n".join(lines)
	text = ""
	try:
		with pdfplumber.open(io.BytesIO(raw)) as pdf:
			text = "\n".join((page.extract_text() or "") for page in pdf.pages[:10])
	except Exception:
		try:
			from pypdf import PdfReader

			text = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(raw)).pages[:10])
		except Exception:
			return ""
	return "\n".join(email_orders.drop_repeats(email_orders.text_item_lines(text))) or text


def _save_files(order, files):
	"""Keep the PDFs on the Email Order (private files) so the order can be checked against them."""
	for name, raw in files:
		frappe.get_doc({"doctype": "File", "file_name": name[:140], "content": raw, "is_private": 1,
		                "attached_to_doctype": "Email Order", "attached_to_name": order.name}).insert(ignore_permissions=True)


def _received(msg: dict):
	ms = msg.get("internalDate")
	if not ms:
		return now_datetime()
	from datetime import datetime, timezone

	return get_datetime(datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).replace(tzinfo=None))


def find_prior(order):
	"""The first earlier email in this Gmail thread, from the same sender, that made an order which
	has not been cancelled: a follow-up in that thread revises it instead of making a second order."""
	if not (order.thread_id and order.sender_email):
		return None
	for name in frappe.get_all("Email Order", filters={
		"thread_id": order.thread_id, "sender_email": order.sender_email, "name": ("!=", order.name),
		"sales_order": ("is", "set"), "status": ("in", ["Draft order", "Needs review", "Revised"]),
	}, order_by="creation asc", pluck="name"):
		prior = frappe.get_doc("Email Order", name)
		if frappe.db.get_value("Sales Order", prior.sales_order, "docstatus") != 2:
			return prior
	return None


def process(order, lead_days: int = 1, prior=None):
	"""Read the order lines, find or create the customer and products, and make the draft Sales Order."""
	lines, unparsed = email_orders.parse_lines(order.body or "")
	order.unparsed = "\n".join(unparsed)
	if not lines:
		order.status = "Needs review"
		order.save(ignore_permissions=True)
		return
	if prior:
		return revise(order, prior, lines, unparsed)
	customer = find_or_create_customer(order.sender_name, order.sender_email)
	order.customer = customer
	order.set("lines", [])
	so_items = []
	for ln in lines:
		item, created = find_or_create_item(customer, ln["external_sku"], ln["description"])
		order.append("lines", {**ln, "item": item, "item_created": 1 if created else 0})
		so_items.append({"item_code": item, "qty": ln["qty"]})
	# the lead time counts from the later of the email date and today: ERPNext rejects a delivery
	# date before the order date, and an email picked up days late is still ordered today
	delivery = add_days(max(getdate(order.received_on or nowdate()), getdate(nowdate())), lead_days)
	so = frappe.get_doc({
		"doctype": "Sales Order", "customer": customer, "delivery_date": str(delivery)[:10],
		"transaction_date": nowdate(), "items": so_items, "hk_email_order": order.name,
	})
	so.insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Sales Order",
	                "reference_name": so.name,
	                "content": _("Picked up from the email '{0}' from {1} ({2}). Check it before submitting.").format(
		                order.subject, order.sender_email, order.name)}).insert(ignore_permissions=True)
	order.sales_order = so.name
	order.status = "Needs review" if unparsed else "Draft order"
	order.save(ignore_permissions=True)


def revise(order, prior, lines, unparsed):
	"""A follow-up email restates the order: the new lines replace the old ones on the same Sales Order
	(a draft is changed; a submitted order is only flagged with the proposal). The earlier items stay in
	Order Revision and the order is flagged for review. An email that changes nothing is ignored."""
	customer = prior.customer
	order.customer, order.revises, order.sales_order = customer, prior.name, prior.sales_order
	order.set("lines", [])
	new_items = []
	for ln in lines:
		item, created = find_or_create_item(customer, ln["external_sku"], ln["description"])
		order.append("lines", {**ln, "item": item, "item_created": 1 if created else 0})
		new_items.append({"item_code": item, "qty": ln["qty"]})
	so = frappe.get_doc("Sales Order", prior.sales_order)
	if so.docstatus == 0:
		so.flags.hk_revision_source = "Email"
		so.flags.hk_revision_email_order = order.name
		so.set("items", [])
		for i in new_items:
			so.append("items", i)
		count = int(so.get("hk_revision_count") or 0)
		so.save(ignore_permissions=True)
		changed = int(so.get("hk_revision_count") or 0) > count
	else:
		rev = revisions_api.record(so.name, revisions_api.lines(so.items), new_items, "Email", applied=0, email_order=order.name)
		changed = bool(rev)
		if rev:
			revisions_api.flag_proposal(so.name, rev)
	order.status = ("Needs review" if (unparsed or so.docstatus != 0) else "Revised") if changed else "Ignored"
	order.save(ignore_permissions=True)


def find_or_create_customer(sender_name: str, address: str) -> str:
	if address:
		found = frappe.db.get_value("Customer", {"email_id": address}, "name")
		if found:
			return found
		rows = frappe.db.sql(
			"""select dl.link_name from `tabContact Email` ce
			   join `tabContact` c on c.name = ce.parent
			   join `tabDynamic Link` dl on dl.parent = c.name and dl.parenttype = 'Contact' and dl.link_doctype = 'Customer'
			   where lower(ce.email_id) = %s limit 1""",
			(address,),
		)
		if rows:
			return rows[0][0]
	title = (sender_name or address or _("Email customer")).strip()
	if frappe.db.exists("Customer", title):
		title = f"{title} ({address})" if address else title
	group = frappe.db.get_single_value("Selling Settings", "customer_group") or frappe.db.get_value(
		"Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_single_value("Selling Settings", "territory") or frappe.db.get_value(
		"Territory", {"is_group": 0}, "name")
	customer = frappe.get_doc({"doctype": "Customer", "customer_name": title, "customer_type": "Company",
	                           "customer_group": group, "territory": territory}).insert(ignore_permissions=True)
	if address:
		frappe.get_doc({
			"doctype": "Contact", "first_name": (sender_name or address)[:60],
			"email_ids": [{"email_id": address, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": customer.name}],
		}).insert(ignore_permissions=True)
	return customer.name


def find_or_create_item(customer: str, external_sku: str, description: str) -> tuple[str, bool]:
	"""(internal SKU = item code, created). Matches this customer's external SKU first, then the
	item name; otherwise creates a sales product with the next SKU-nnnn and records the external SKU."""
	external_sku = sku.clean(external_sku)
	description = (description or "").strip()
	found = None
	if external_sku:
		found = frappe.db.get_value("Item Customer Detail", {"customer_name": customer, "ref_code": external_sku,
		                                                     "parenttype": "Item"}, "parent")
	if not found and description:
		found = frappe.db.get_value("Item", {"item_name": description, "disabled": 0}, "name")
	if found:
		if external_sku and not frappe.db.exists("Item Customer Detail", {"parent": found, "customer_name": customer,
		                                                                  "ref_code": external_sku}):
			item = frappe.get_doc("Item", found)
			item.append("customer_items", {"customer_name": customer, "ref_code": external_sku})
			item.save(ignore_permissions=True)
		return found, False
	codes = frappe.get_all("Item", filters={"name": ("like", f"{CODE_PREFIX}%")}, pluck="name")
	company = frappe.defaults.get_global_default("company")
	item = frappe.get_doc({
		"doctype": "Item", "item_code": sku.next_code(codes, CODE_PREFIX), "item_name": (description or external_sku)[:140],
		"item_group": PRODUCT_GROUP, "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 0,
		"customer_items": [{"customer_name": customer, "ref_code": external_sku}] if external_sku else [],
		"item_defaults": [{"company": company}] if company else [],
	}).insert(ignore_permissions=True)
	return item.name, True


# --- entry points ------------------------------------------------------------------------

def scheduled_fetch():
	"""Every 15 minutes: does nothing until Gmail Settings is switched on and complete."""
	s = frappe.get_single("Gmail Settings")
	if not s.enabled:
		return
	try:
		fetch()
	except Exception:
		frappe.log_error(title="Gmail order pick-up")


@frappe.whitelist()
def fetch_now() -> dict:
	frappe.only_for("System Manager")
	return fetch()


@frappe.whitelist()
def test_connection() -> str:
	frappe.only_for("System Manager")
	s = frappe.get_single("Gmail Settings")
	return GmailClient(s).profile()


@frappe.whitelist()
def reprocess(name: str):
	"""Read an Email Order again from Gmail (new reading rules, or its PDFs): only while it has no
	Sales Order and is Needs review or Failed. Replaces its body, PDFs and lines; makes the draft order."""
	frappe.only_for(("Sales Manager", "System Manager"))
	order = frappe.get_doc("Email Order", name)
	if order.sales_order or order.status not in ("Needs review", "Failed"):
		frappe.throw(_("Only an email without a sales order that is Needs review or Failed can be read again."))
	s = frappe.get_single("Gmail Settings")
	client = GmailClient(s)
	payload = client.get_message(order.message_id).get("payload") or {}
	files = _pdf_files(client, order.message_id, payload)
	order.body = email_orders.join_attachment_text(
		email_orders.body_text(payload), [(n, pdf_text(raw)) for n, raw in files])
	order.error = ""
	order.save(ignore_permissions=True)
	if not frappe.get_all("File", filters={"attached_to_doctype": "Email Order", "attached_to_name": order.name}):
		_save_files(order, files)
	process(order, lead_days=int(s.default_lead_days or 1), prior=find_prior(order))
	return frappe.db.get_value("Email Order", name, "status")
