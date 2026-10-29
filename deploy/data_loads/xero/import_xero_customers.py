"""Idempotent load of Xero customer contacts into ERPNext Customers.

Input: Xero's contact export CSV (Contacts > Customers > Export), any column order.
Run inside the backend container (copy both files to /tmp first):
    bench --site <site> console   then:
        exec(open("/tmp/import_xero_customers.py").read()); run("/tmp/xero_contacts.csv", dry_run=True)
dry_run=True does every insert and then rolls back, so real errors show up.
dry_run=False commits.

Matching (no duplicates): the Xero contact ID noted on the customer, then the customer name
(case and spacing ignored). A new customer whose email already belongs to a non-Xero customer
(e.g. one made by Email Orders) is listed under "check" for a person to merge; several Xero
outlets share one buyer's email, so email alone is not used to merge.
Junk names and our own company names (EXCLUDE) are skipped, and so are emails on our own domains. Existing customers only get empty fields filled; an
address or contact is added only when the customer has none of that kind yet.
"""
import csv
import re

import frappe

ERRORS = []
REPORT = {"created": [], "updated": [], "skipped": [], "check": []}
GROUP = "Xero Customers"
# Not customers: placeholder/junk names created by email parsing, and our own company names.
EXCLUDE = {"monthly statement", "company name", "date", "---------- forwarded message ---------",
           "unknown_contact", "happy", "happy concepts food limited", "happy concepts food ltd",
           "happy concepts (happy-concepts.com / orders@happyconceptsfood.hk)", "happy concepts asia ltd",
           "happy concepts asia ltd.", "happy concepts asia limited", "happy concepts"}
# Our own staff addresses sometimes sit on customer contacts in Xero; keep them off ERP contacts,
# or Email Orders would match our own emails to that customer.
INTERNAL_DOMAINS = ("happyconceptsfood.hk", "happy-concepts.com")
TERM_ALIASES = {"DAYSAFTER": "DAYSAFTERBILLDATE", "DAYSAFTERTHEBILLDATE": "DAYSAFTERBILLDATE",
                "DAYSAFTERTHEENDOFTHEBILLMONTH": "DAYSAFTERBILLMONTH", "OFTHEFOLLOWINGMONTH": "OFFOLLOWINGMONTH",
                "OFTHECURRENTMONTH": "OFCURRENTMONTH"}
TERM_TYPES = {  # Xero DueDateSalesTerm -> (template name pattern, ERPNext due_date_based_on)
	"DAYSAFTERBILLDATE": ("Net {d}", "Day(s) after invoice date"),
	"DAYSAFTERBILLMONTH": ("{d} days after month end", "Day(s) after the end of the invoice month"),
	"OFFOLLOWINGMONTH": ("{d} of following month", "Month(s) after the end of the invoice month"),
	"OFCURRENTMONTH": ("{d} of current month", "Day(s) after invoice date"),
}


def _norm(s):
	return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _get(row, *names):
	for n in names:
		v = row.get(_norm(n))
		if v not in (None, ""):
			return v.strip()
	return ""


def _guarded(label, fn):
	sp = "xc_" + frappe.generate_hash(length=8)
	frappe.db.savepoint(sp)
	try:
		fn()
		return True
	except Exception as e:
		frappe.db.rollback(save_point=sp)
		frappe.clear_messages()
		ERRORS.append(f"{label}: {type(e).__name__}: {str(e)[:300]}")
		return False


def _clean_email(s):
	for part in re.split(r"[;,/ ]+", s or ""):
		if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", part) and not part.lower().endswith(INTERNAL_DOMAINS):
			return part.lower()
	return ""


def _phone(row, prefix):
	parts = [_get(row, f"{prefix}CountryCode"), _get(row, f"{prefix}AreaCode"), _get(row, f"{prefix}Number", prefix)]
	return " ".join(p for p in parts if p)[:140]


def _country(name):
	if not name:
		return "Hong Kong"
	hit = frappe.db.get_value("Country", {"name": name}) or frappe.db.get_value("Country", {"code": name.lower()})
	return hit or "Hong Kong"


def _ensure_group():
	if frappe.db.exists("Customer Group", GROUP):
		return
	root = frappe.db.get_value("Customer Group", {"is_group": 1, "parent_customer_group": ["in", ["", None]]}, "name") \
		or "All Customer Groups"
	frappe.get_doc({"doctype": "Customer Group", "customer_group_name": GROUP, "parent_customer_group": root,
	                "is_group": 0}).insert(ignore_permissions=True)


def _terms(row):
	day, term = _get(row, "DueDateSalesDay"), _get(row, "DueDateSalesTerm").upper().replace(" ", "")
	term = TERM_ALIASES.get(term, term)
	if not day or term not in TERM_TYPES:
		return ""
	try:
		d = int(float(day))
	except ValueError:
		return ""
	pattern, based_on = TERM_TYPES[term]
	name = pattern.format(d=d)
	if term == "OFFOLLOWINGMONTH":
		pt = {"due_date_based_on": "Day(s) after the end of the invoice month", "credit_days": d}
	elif term == "OFCURRENTMONTH":
		pt = {"due_date_based_on": "Day(s) after invoice date", "credit_days": 0}
	else:
		pt = {"due_date_based_on": based_on, "credit_days": d}
	if not frappe.db.exists("Payment Terms Template", name):
		frappe.get_doc({"doctype": "Payment Terms Template", "template_name": name, "terms": [
			{"invoice_portion": 100, "description": f"Xero: {d} {term}", **pt}]}).insert(ignore_permissions=True)
	return name


def _find(row, name, email, xero_id, account):
	if xero_id:
		hit = frappe.db.get_value("Customer", {"customer_details": ["like", f"%Xero contact ID: {xero_id}%"]}, "name")
		if hit:
			return hit
	target = _norm(name)
	for cname, cn in frappe.db.sql("select name, customer_name from tabCustomer"):
		if _norm(cn) == target or _norm(cname) == target:
			return cname
	return None


def _email_match(email):
	"""Existing non-Xero customer with this email (e.g. made by Email Orders): reported, not merged,
	because several Xero outlets share one buyer's email."""
	if not email:
		return None
	rows = frappe.db.sql(
		"""select distinct c.name from `tabCustomer` c
		   left join `tabDynamic Link` dl on dl.link_doctype = 'Customer' and dl.link_name = c.name and dl.parenttype = 'Contact'
		   left join `tabContact Email` ce on ce.parent = dl.parent
		   where (lower(c.email_id) = %s or lower(ce.email_id) = %s)
		     and ifnull(c.customer_details, '') not like '%%Imported from Xero%%'""", (email, email))
	return ", ".join(r[0] for r in rows) or None


def _has(link_name, parenttype):
	return frappe.db.exists("Dynamic Link", {"link_doctype": "Customer", "link_name": link_name, "parenttype": parenttype})


def _address(row, prefix, title, link, kind, email, phone):
	line1 = _get(row, f"{prefix}AddressLine1")
	if not line1:
		return
	extra = ", ".join(x for x in (_get(row, f"{prefix}AddressLine2"), _get(row, f"{prefix}AddressLine3"),
	                               _get(row, f"{prefix}AddressLine4")) if x)
	frappe.get_doc({"doctype": "Address", "address_title": title[:100], "address_type": kind,
	                "address_line1": line1[:240], "address_line2": extra[:240],
	                "city": (_get(row, f"{prefix}City") or "Hong Kong")[:140], "state": _get(row, f"{prefix}Region")[:140],
	                "pincode": _get(row, f"{prefix}PostalCode", f"{prefix}ZipCode")[:140],
	                "country": _country(_get(row, f"{prefix}Country")), "email_id": email, "phone": phone,
	                "is_primary_address": 1 if kind == "Billing" else 0,
	                "is_shipping_address": 1 if kind == "Shipping" else 0,
	                "links": [link]}).insert(ignore_permissions=True)


def _contacts(row, name, link, email, phone, mobile):
	people = []
	first, last = _get(row, "FirstName"), _get(row, "LastName")
	if first or last or email or phone or mobile:
		people.append((first or name, last, email, True))
	for i in range(1, 6):
		pf, pl, pe = _get(row, f"Person{i}FirstName"), _get(row, f"Person{i}LastName"), _clean_email(_get(row, f"Person{i}Email"))
		if pf or pl or pe:
			people.append((pf or pe or name, pl, pe, False))
	for fn, ln, em, primary in people:
		c = {"doctype": "Contact", "first_name": fn[:140], "last_name": ln[:140], "links": [link],
		     "is_primary_contact": 1 if primary else 0}
		if em:
			c["email_ids"] = [{"email_id": em, "is_primary": 1}]
		if primary:
			nos = []
			if phone:
				nos.append({"phone": phone, "is_primary_phone": 1})
			if mobile:
				nos.append({"phone": mobile, "is_primary_mobile_no": 1})
			c["phone_nos"] = nos
		frappe.get_doc(c).insert(ignore_permissions=True)


def load(rows):
	group = GROUP
	territory = ("Hong Kong" if frappe.db.exists("Territory", "Hong Kong") else None) or \
		frappe.db.get_single_value("Selling Settings", "territory") or frappe.db.get_value(
		"Territory", {"is_group": 0}, "name") or "All Territories"
	seen = set()
	for row in rows:
		name = _get(row, "ContactName", "Name")[:140]
		if not name:
			REPORT["skipped"].append("(row without a name)")
			continue
		if _norm(name) in seen:
			REPORT["skipped"].append(f"{name}: duplicate row in the export")
			continue
		seen.add(_norm(name))
		if name.strip().lower() in EXCLUDE:
			REPORT["skipped"].append(f"{name}: not a customer (junk or own company)")
			continue
		status = _get(row, "ContactStatus", "Status").upper()
		if status in ("ARCHIVED", "GDPRREQUEST"):
			REPORT["skipped"].append(f"{name}: archived in Xero")
			continue

		def one(row=row, name=name):
			email = _clean_email(_get(row, "EmailAddress", "Email"))
			phone = _phone(row, "Phone")
			mobile = _phone(row, "Mobile")
			xero_id = _get(row, "ContactID")
			account = _get(row, "AccountNumber")
			details = [f"Imported from Xero on {frappe.utils.today()}."]
			for label, val in (("Xero contact ID", xero_id), ("Xero account number", account),
			                   ("Fax", _phone(row, "Fax")), ("Website", _get(row, "Website")),
			                   ("Company number", _get(row, "CompanyNumber")), ("Discount", _get(row, "Discount")),
			                   ("Sales account", _get(row, "SalesAccount")),
			                   ("Payment terms in Xero", " ".join(x for x in (_get(row, "DueDateSalesDay"), _get(row, "DueDateSalesTerm")) if x))):
				if val:
					details.append(f"{label}: {val}")
			vals = {"customer_group": group, "territory": territory, "customer_type": "Company",
			        "tax_id": _get(row, "TaxNumber")[:140], "default_currency": (_get(row, "DefaultCurrency", "Currency") or "HKD")[:3].upper(),
			        "payment_terms": _terms(row), "website": _get(row, "Website")[:140]}
			if vals["default_currency"] and not frappe.db.exists("Currency", vals["default_currency"]):
				vals["default_currency"] = ""
			existing = _find(row, name, email, xero_id, account)
			if existing:
				doc = frappe.get_doc("Customer", existing)
				for k, v in vals.items():
					if v and not doc.get(k) and k != "customer_group":
						doc.set(k, v)
				if not (doc.customer_details or "").strip():
					doc.customer_details = "\n".join(details)
				elif xero_id and xero_id not in doc.customer_details:
					doc.customer_details += "\n" + "\n".join(details)
				doc.save(ignore_permissions=True)
				REPORT["updated"].append(f"{name} -> {existing}")
			else:
				other = _email_match(email)
				if other:
					REPORT["check"].append(f"{name}: same email as existing customer {other}")
				doc = frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_details": "\n".join(details),
				                      **{k: v for k, v in vals.items() if v}}).insert(ignore_permissions=True)
				existing = doc.name
				REPORT["created"].append(name)
			link = {"link_doctype": "Customer", "link_name": existing}
			if not _has(existing, "Address"):
				_address(row, "PO", name, link, "Billing", email, phone)
				_address(row, "SA", name, link, "Shipping", email, phone)
			if not _has(existing, "Contact"):
				_contacts(row, name, link, email, phone, mobile)

		_guarded(name, one)


def run(path, dry_run=True):
	ERRORS.clear()
	for v in REPORT.values():
		v.clear()
	with open(path, encoding="utf-8-sig", newline="") as f:
		rows = [{_norm(k): (v or "") for k, v in r.items() if k} for r in csv.DictReader(f)]
	frappe.flags.in_import = True
	_ensure_group()
	load(rows)
	print(f"rows: {len(rows)}  created: {len(REPORT['created'])}  updated: {len(REPORT['updated'])}  "
	      f"skipped: {len(REPORT['skipped'])}  errors: {len(ERRORS)}")
	for k in ("updated", "skipped", "check"):
		for line in REPORT[k]:
			print(f"  {k}: {line}")
	for e in ERRORS:
		print("  ERROR", e)
	if dry_run:
		frappe.db.rollback()
		print("DRY RUN, nothing saved")
	else:
		frappe.db.commit()
		print("committed")
	return {**{k: len(v) for k, v in REPORT.items()}, "errors": len(ERRORS)}
