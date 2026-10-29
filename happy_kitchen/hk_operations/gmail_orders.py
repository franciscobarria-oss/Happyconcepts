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
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime, nowdate

from happy_kitchen.hk_operations import email_orders, order_prices, revisions_api, sku

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
PRODUCT_GROUP = "Products"
CODE_PREFIX = "SKU-"
MIN_SHARED_PO = 6  # a PO number this long is taken as unique across customers (short ones can repeat)
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


def build_query(label: str, look_back_days: int, extra_senders: str | None = None) -> str:
	return email_orders.search_query(label, look_back_days, extra_senders)


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
		ids = client.list_ids(build_query(s.label_name, s.look_back_days, s.extra_senders), int(s.max_per_run or 25))
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
	subject = email_orders.header(payload, "Subject") or _("(no subject)")
	name, address, via = email_orders.original_sender(payload, subject, s.skip_reply_senders)
	order = frappe.get_doc({
		"doctype": "Email Order", "message_id": message_id, "status": "New",
		"subject": subject[:140],
		"sender_name": name, "sender_email": address, "forwarded_by": via,
		"received_on": _received(payload_msg), "thread_id": payload_msg.get("threadId"),
	})
	if not email_orders.sender_allowed(via or address, s.allowed_senders):
		order.status = "Ignored"
		order.insert(ignore_permissions=True)
		return order.status
	if email_orders.skip_reply(via or address, order.subject, payload, bool(email_orders.pdf_attachments(payload)), s.skip_reply_senders):
		order.status = "Ignored"
		order.insert(ignore_permissions=True)
		return order.status
	files = _pdf_files(client, message_id, payload)
	order.body = email_orders.join_attachment_text(
		email_orders.body_text(payload, forward=email_orders.is_forward(subject)), [(n, pdf_text(raw)) for n, raw in files])
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

	rows, texts = [], []
	try:
		with pdfplumber.open(io.BytesIO(raw)) as pdf:
			for page in pdf.pages[:10]:
				texts.append(page.extract_text() or "")
				for table in page.extract_tables() or []:
					rows += table
	except Exception:
		rows = []
	lines = email_orders.table_to_lines(rows)
	if lines:
		# a table PDF is one purchase order: its number and delivery date come from the page text
		whole = "\n".join(texts)
		po, date = email_orders.po_number(whole), email_orders.delivery_date_of(whole)
		return "\n".join(([f"--- PO {po}{' | ' + date if date else ''} ---"] if po else []) + lines)
	pages = []
	try:
		with pdfplumber.open(io.BytesIO(raw)) as pdf:
			pages = [(page.extract_text() or "") for page in pdf.pages[:10]]
	except Exception:
		try:
			from pypdf import PdfReader

			pages = [(page.extract_text() or "") for page in PdfReader(io.BytesIO(raw)).pages[:10]]
		except Exception:
			return ""
	out = []
	for po, date, page_lines in email_orders.text_item_pages(pages):
		if page_lines:
			out += ([f"--- PO {po}{' | ' + date if date else ''} ---"] if po else []) + page_lines
	return "\n".join(out) or "\n".join(pages)


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
	"""Read the order lines, find or create the customer and products, and make the draft Sales Order(s):
	one per purchase order number in the email or its PDFs (lines without a PO number are one order).
	A follow-up in the same thread revises the earlier order only when it carries no PO numbers."""
	lines, unparsed = email_orders.parse_lines(order.body or "")
	order.unparsed = "\n".join(unparsed)
	if not lines:
		order.status = "Needs review"
		order.save(ignore_permissions=True)
		return
	if prior and not any(ln["po_no"] for ln in lines):
		return revise(order, prior, lines, unparsed)
	customer, customer_note = resolve_customer(order)
	if not customer:
		order.unparsed = "\n".join(([order.unparsed] if order.unparsed else []) + [customer_note])
		order.status = "Needs review"
		order.save(ignore_permissions=True)
		return
	order.customer = customer
	order.set("lines", [])
	groups = {}
	for ln in lines:
		groups.setdefault(ln["po_no"], []).append(ln)
	notes, made = ([customer_note] if customer_note else []), []
	for po, group in groups.items():
		if po and frappe.db.exists("Sales Order", {"customer": customer, "po_no": po, "docstatus": ("<", 2)}):
			notes.append(_("PO {0} already has a sales order.").format(po))
			continue
		other = po and len(po) >= MIN_SHARED_PO and frappe.db.get_value(
			"Sales Order", {"po_no": po, "docstatus": ("<", 2)}, ["name", "customer"], as_dict=True)
		if other:
			notes.append(_("PO {0} already has sales order {1} under {2}: check the customer.").format(po, other.name, other.customer))
			continue
		items = []
		for ln in group:
			item, created = find_or_create_item(customer, ln["external_sku"], ln["description"])
			items.append((ln, item, created))
		so = _make_sales_order(order, customer, po, items, lead_days)
		made.append(so.name)
		for (ln, item, created), chk in zip(items, so.flags.hk_price_checks):
			order.append("lines", {**ln, "item": item, "item_created": 1 if created else 0,
			                       "delivery_date": ln["delivery_date"] or None, "sales_order": so.name,
			                       "our_rate": chk["our_rate"], "price_check": chk["status"]})
	if notes:
		order.unparsed = "\n".join(([order.unparsed] if order.unparsed else []) + notes)
	if not made:
		order.status = "Ignored"
		order.save(ignore_permissions=True)
		return
	order.sales_order = made[0]
	order.status = "Needs review" if unparsed or notes else "Draft order"
	order.save(ignore_permissions=True)


def _make_sales_order(order, customer, po, items, lead_days):
	"""One draft Sales Order for one PO. A delivery date from the PO is used when it is today or later,
	otherwise the lead time counts from the later of the email date and today (ERPNext rejects a delivery
	date before the order date, and an email picked up days late is still ordered today)."""
	today = getdate(nowdate())
	fallback = add_days(max(getdate(order.received_on or nowdate()), today), lead_days)

	def usable(d):
		return d if d and getdate(d) >= today else None

	so_items = []
	for ln, item, _created in items:
		row = {"item_code": item, "qty": ln["qty"], "hk_po_rate": flt(ln.get("po_rate"))}
		if usable(ln["delivery_date"]):
			row["delivery_date"] = ln["delivery_date"]
		so_items.append(row)
	dates = [r["delivery_date"] for r in so_items if r.get("delivery_date")]
	delivery = min(dates) if dates else fallback
	so = frappe.get_doc({
		"doctype": "Sales Order", "customer": customer, "delivery_date": str(delivery)[:10], "po_no": po or None,
		"transaction_date": nowdate(), "items": so_items, "hk_email_order": order.name,
	})
	so.insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Sales Order",
	                "reference_name": so.name,
	                "content": _("Picked up from the email '{0}' from {1} ({2}). Check it before submitting.").format(
		                order.subject, order.sender_email, order.name)}).insert(ignore_permissions=True)
	so.flags.hk_price_checks = apply_po_prices(so)
	return so


def apply_po_prices(so, rows=None) -> list[dict]:
	"""Each Sales Order row (in order; or only `rows`) checked against the customer's PO price
	(order_prices.check): a row without a price of ours takes the PO price; a different price keeps ours
	and is only reported. The order is saved when a price was filled, and a comment lists what was filled
	or differs. Never blocks."""
	checks, filled, notes = [], False, []
	for row in (so.items if rows is None else rows):
		chk = order_prices.check(row.get("hk_po_rate"), row.rate)
		chk["our_rate"] = flt(row.rate)
		name = row.item_name or row.item_code
		if chk["fill"]:
			row.rate = chk["rate"]
			filled = True
			notes.append(_("{0}: no price of ours, the PO price {1} was used").format(name, order_prices.money(chk["rate"])))
		elif chk["status"] == order_prices.DIFFERS:
			notes.append(_("{0}: PO price {1}, our price {2} ({3})").format(
				name, order_prices.money(row.hk_po_rate), order_prices.money(row.rate), order_prices.signed(chk)))
		checks.append(chk)
	if filled:
		so.save(ignore_permissions=True)
	if notes:
		frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Sales Order",
		                "reference_name": so.name,
		                "content": _("Prices checked against the customer's PO:") + "<br>" + "<br>".join(
			                frappe.utils.escape_html(n) for n in notes)}).insert(ignore_permissions=True)
	return checks


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
		new_items.append({"item_code": item, "qty": ln["qty"], "hk_po_rate": flt(ln.get("po_rate"))})
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
		for line, chk in zip(order.lines, apply_po_prices(so)):
			line.our_rate, line.price_check = chk["our_rate"], chk["status"]
	else:
		rev = revisions_api.record(so.name, revisions_api.lines(so.items), new_items, "Email", applied=0, email_order=order.name)
		changed = bool(rev)
		if rev:
			revisions_api.flag_proposal(so.name, rev)
	order.status = ("Needs review" if (unparsed or so.docstatus != 0) else "Revised") if changed else "Ignored"
	order.save(ignore_permissions=True)


def _email_customers(address: str) -> list[str]:
	"""Customers that have this email: on the Customer itself or on a Contact linked to it."""
	if not address:
		return []
	found = frappe.get_all("Customer", filters={"email_id": address, "disabled": 0}, pluck="name")
	rows = frappe.db.sql(
		"""select distinct dl.link_name from `tabContact Email` ce
		   join `tabContact` c on c.name = ce.parent
		   join `tabDynamic Link` dl on dl.parent = c.name and dl.parenttype = 'Contact' and dl.link_doctype = 'Customer'
		   join `tabCustomer` cu on cu.name = dl.link_name and cu.disabled = 0
		   where lower(ce.email_id) = %s order by dl.link_name""",
		(address.lower(),),
	)
	return list(dict.fromkeys(found + [r[0] for r in rows]))


def _outlet_phrases(names: list[str] | None = None) -> list[tuple[str, list[str]]]:
	"""[(customer, [customer name, names in order emails, shipping address first lines])]."""
	filters = {"disabled": 0}
	if names is not None:
		filters["name"] = ("in", names or [""])
	out = {}
	for c in frappe.get_all("Customer", filters=filters, fields=["name", "customer_name", "hk_order_names"]):
		if email_orders.VIA_NAME.match(c.customer_name or ""):
			continue  # never match an old "'Name' via Orders" placeholder customer
		out[c.name] = [c.customer_name, *email_orders.order_names(c.hk_order_names)]
	if out:
		for a in frappe.db.sql(
			"""select dl.link_name, a.address_line1 from `tabAddress` a
			   join `tabDynamic Link` dl on dl.parent = a.name and dl.parenttype = 'Address' and dl.link_doctype = 'Customer'
			   where a.disabled = 0 and dl.link_name in %s and char_length(a.address_line1) >= 10""",
			(tuple(out),), as_dict=True,
		):
			out[a.link_name].append(a.address_line1)
	return list(out.items())


def resolve_customer(order) -> tuple[str, str]:
	"""(customer, note) for an email order. The outlet named in the order (customer name, its "names in
	order emails" or a shipping address line found in the email or PDF) wins among the customers that
	have the sender's email; then the sender's only customer; then the outlet named anywhere; else a new
	customer from the sender. The note asks for a check when the customer is new on a forwarded mail."""
	text = "\n".join([order.subject or "", order.body or ""])
	by_email = [c for c in _email_customers(order.sender_email)
	            if not email_orders.VIA_NAME.match(frappe.db.get_value("Customer", c, "customer_name") or "")]
	if by_email:
		named = email_orders.match_outlet(text, _outlet_phrases(by_email))
		if named:
			return named, ""
		if len(by_email) == 1:
			return by_email[0], ""
	named = email_orders.match_outlet(text, _outlet_phrases())
	if named:
		return named, ""
	if by_email:
		return by_email[0], _("The sender's email belongs to several customers ({0}); {1} was used: check it.").format(
			", ".join(by_email), by_email[0])
	if order.get("forwarded_by") and not order.sender_email:
		# a group mail without its author's address: never make a customer from the group
		return None, _("Forwarded through {0} without the original sender's address, and no outlet name was found: enter it by hand, or add the outlet's name under the customer's Names in order emails and Read again.").format(order.forwarded_by)
	customer = find_or_create_customer(order.sender_name, order.sender_email)
	note = ""
	if order.get("forwarded_by"):
		note = _("New customer {0} made from the original sender of a forwarded email: check it, or add the outlet's name under the customer's Names in order emails.").format(customer)
	return customer, note


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
	if not found and external_sku:
		found = _known_code(external_sku)
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


def _known_code(code: str) -> str | None:
	"""A real item for a customer's code that this customer has not used yet: the code is our own item
	code, or exactly one real item carries it for another customer (outlets of one chain share codes).
	Placeholder items made by the pick-up (SKU-nnnn) never count."""
	if not code.startswith(CODE_PREFIX) and frappe.db.exists("Item", {"name": code, "disabled": 0, "is_sales_item": 1}):
		return code
	parents = {p for p in frappe.get_all("Item Customer Detail", filters={"ref_code": code, "parenttype": "Item"}, pluck="parent")
	           if not p.startswith(CODE_PREFIX) and not frappe.db.get_value("Item", p, "disabled")}
	return parents.pop() if len(parents) == 1 else None


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
	subject = email_orders.header(payload, "Subject") or order.subject or ""
	order.sender_name, order.sender_email, order.forwarded_by = email_orders.original_sender(
		payload, subject, s.skip_reply_senders)
	files = _pdf_files(client, order.message_id, payload)
	order.body = email_orders.join_attachment_text(
		email_orders.body_text(payload, forward=email_orders.is_forward(subject)), [(n, pdf_text(raw)) for n, raw in files])
	order.error = ""
	order.save(ignore_permissions=True)
	if not frappe.get_all("File", filters={"attached_to_doctype": "Email Order", "attached_to_name": order.name}):
		_save_files(order, files)
	process(order, lead_days=int(s.default_lead_days or 1), prior=find_prior(order))
	return frappe.db.get_value("Email Order", name, "status")


@frappe.whitelist()
def review_data(name: str) -> dict:
	"""Everything the review screen on an Email Order shows: the email, its files, and what the system understood."""
	order = frappe.get_doc("Email Order", name)
	order.check_permission("read")
	files = frappe.get_all("File", filters={"attached_to_doctype": "Email Order", "attached_to_name": name},
	                       fields=["file_name", "file_url"], order_by="creation asc")
	body = order.body or ""
	text, _sep, attached = body.partition("--- Attachment:")
	attached = ("--- Attachment:" + attached) if _sep else ""
	lines = [{"external_sku": l.external_sku, "description": l.description, "qty": l.qty, "item": l.item, "po_no": l.po_no,
	          "delivery_date": str(l.delivery_date or ""), "sales_order": l.sales_order, "idx": l.idx,
		          "item_created": l.item_created, "item_confirmed": l.item_confirmed,
		          "po_rate": flt(l.po_rate), "our_rate": flt(l.our_rate), "price_check": l.price_check or "",
		          "item_name": frappe.db.get_value("Item", l.item, "item_name") if l.item else ""} for l in order.lines]
	unparsed = [u for u in (order.unparsed or "").split("\n") if u.strip()]
	pdfs = [f for f in files if (f.file_name or "").lower().endswith(".pdf")]
	prices = order_prices.counts(l["price_check"] for l in lines)
	reasons = email_orders.review_reasons(order.status, len(lines), len(unparsed), bool(order.sales_order), len(pdfs),
	                                      bool(attached.strip()), prices)
	counts = {"{unparsed}": len(unparsed), "{differs}": prices[order_prices.DIFFERS], "{used}": prices[order_prices.USED],
	          "{none}": prices[order_prices.NONE]}

	def fill(r):
		r = _(r)
		for k, v in counts.items():
			r = r.replace(k, str(v))
		return r

	return {"status": order.status, "files": files, "email_text": text.strip()[:6000], "pdf_text": attached.strip()[:12000],
	        "lines": lines, "unparsed": unparsed, "reasons": [fill(r) for r in reasons], "sales_order": order.sales_order,
	        "price_differs": prices[order_prices.DIFFERS],
	        "customer": order.customer, "error": order.error}


@frappe.whitelist()
def mark_done_by_hand(name: str, sales_order: str | None = None):
	"""Close an email whose order a person entered by hand, so it leaves the Today count."""
	frappe.only_for(("Sales Manager", "System Manager"))
	order = frappe.get_doc("Email Order", name)
	if order.status not in ("Needs review", "Failed"):
		frappe.throw(_("Only an email that is Needs review or Failed can be marked as entered by hand."))
	if sales_order and not frappe.db.exists("Sales Order", sales_order):
		frappe.throw(_("Sales Order {0} does not exist.").format(sales_order))
	order.status = "Done by hand"
	if sales_order and not order.sales_order:
		order.sales_order = sales_order
	order.save(ignore_permissions=True)
	order.add_comment("Comment", _("Marked as entered by hand by {0}.").format(frappe.utils.get_fullname(frappe.session.user)))
	return order.status


@frappe.whitelist()
def mark_not_order(name: str):
	"""Close an email that is not an order (a note, a reply), so it leaves the Today count."""
	frappe.only_for(("Sales Manager", "System Manager"))
	order = frappe.get_doc("Email Order", name)
	if order.status not in ("Needs review", "Failed"):
		frappe.throw(_("Only an email that is Needs review or Failed can be marked as not an order."))
	order.status = "Ignored"
	order.save(ignore_permissions=True)
	order.add_comment("Comment", _("Marked as not an order by {0}.").format(frappe.utils.get_fullname(frappe.session.user)))
	return order.status


@frappe.whitelist()
def confirm_line_item(name: str, idx: int, item: str | None = None):
	"""Confirm the product the reader chose for a line, or change it to another item.
	A change also moves the customer's code to the new item and fixes the draft Sales Order row."""
	frappe.only_for(("Sales Manager", "System Manager"))
	order = frappe.get_doc("Email Order", name)
	line = next((l for l in order.lines if l.idx == int(idx)), None)
	if not line:
		frappe.throw(_("Line {0} not found.").format(idx))
	old = line.item
	if item and item != old:
		if not frappe.db.exists("Item", item):
			frappe.throw(_("Item {0} does not exist.").format(item))
		so = frappe.get_doc("Sales Order", line.sales_order) if line.sales_order else None
		if so and so.docstatus != 0:
			frappe.throw(_("The sales order {0} is already submitted. Change the item on the order itself.").format(so.name))
		code = sku.clean(line.external_sku)
		if code and order.customer:
			frappe.db.delete("Item Customer Detail", {"parent": old, "parenttype": "Item", "customer_name": order.customer, "ref_code": code})
			if not frappe.db.exists("Item Customer Detail", {"parent": item, "customer_name": order.customer, "ref_code": code}):
				new = frappe.get_doc("Item", item)
				new.append("customer_items", {"customer_name": order.customer, "ref_code": code})
				new.save(ignore_permissions=True)
		if so:
			new_row = None
			for row in so.items:
				if row.item_code == old and flt(row.qty) == flt(line.qty):
					delivery = row.delivery_date
					so.remove(row)
					new_row = so.append("items", {"item_code": item, "qty": line.qty, "delivery_date": delivery,
					                              "hk_po_rate": flt(line.po_rate)})
					break
			so.save(ignore_permissions=True)
			if new_row:
				# the new item's own price, then the PO price check for that row only
				new_row = next(r for r in so.items if r.name == new_row.name)
				chk = apply_po_prices(so, [new_row])[0]
				line.our_rate, line.price_check = chk["our_rate"], chk["status"]
		line.item = item
		line.item_created = 0
	line.item_confirmed = 1
	order.save(ignore_permissions=True)
	return line.item


@frappe.whitelist()
def confirm_order(name: str):
	"""A person checked the email against the PDF and the order is right: confirm every line's item, submit the
	draft Sales Order(s) the email made (one per PO) and close the email. All or nothing: if one order cannot
	be submitted, nothing is changed and the reason is shown."""
	frappe.only_for(("Sales Manager", "System Manager"))
	order = frappe.get_doc("Email Order", name)
	if order.status not in ("Draft order", "Revised", "Needs review", "Failed"):
		frappe.throw(_("This email cannot be marked as order confirmed."))
	names = sorted({l.sales_order for l in order.lines if l.sales_order} | ({order.sales_order} if order.sales_order else set()))
	submitted = []
	for so_name in names:
		so = frappe.get_doc("Sales Order", so_name)
		if so.docstatus != 0:
			continue
		try:
			so.submit()
		except Exception as e:
			frappe.db.rollback()
			frappe.throw(_("Sales Order {0} could not be submitted: {1}").format(so_name, str(e)[:300]))
		submitted.append(so_name)
	order = frappe.get_doc("Email Order", name)
	for line in order.lines:
		if line.item:
			line.item_confirmed = 1
	order.status = "Order confirmed"
	order.save(ignore_permissions=True)
	note = _("Order confirmed by {0}.").format(frappe.utils.get_fullname(frappe.session.user))
	if submitted:
		note += " " + _("Submitted: {0}.").format(", ".join(submitted))
	order.add_comment("Comment", note)
	return order.status


@frappe.whitelist()
def confirm_po(name: str, po_no: str = ""):
	"""Confirm the items of the lines on one PO (one page of the order). Lines with no PO number are po_no ''."""
	frappe.only_for(("Sales Manager", "System Manager"))
	order = frappe.get_doc("Email Order", name)
	changed = 0
	for line in order.lines:
		if (line.po_no or "") == (po_no or "") and line.item and not line.item_confirmed:
			line.item_confirmed = 1
			changed += 1
	if changed:
		order.save(ignore_permissions=True)
	return changed
