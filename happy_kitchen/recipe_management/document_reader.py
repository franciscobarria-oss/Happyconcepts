"""Document reader: upload a PDF or image, Gemini reads it like OCR and returns the text plus tables.

Uses the Gemini key and model already set in Gmail Settings (shared with the scanned-PDF and recipe photo readers).
Nothing is saved except the uploaded File; the screen offers the text, and each table as CSV / Excel / copy."""
from __future__ import annotations

import base64
import json

import frappe
from frappe import _

from happy_kitchen.hk_operations import pdf_ocr
from happy_kitchen.recipe_management import document_rules as rules
from happy_kitchen.recipe_management import photo_reader

ROLES = ("System Manager", "Manufacturing Manager", "Manufacturing User", "Stock Manager", "Stock User",
         "Purchase Manager", "Purchase User", "Sales Manager", "Sales User", "Accounts Manager", "Accounts User")
MAX_BYTES = 15 * 1024 * 1024


def _check():
	if not set(frappe.get_roles()) & set(ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def read_bytes(raw: bytes, filename: str = "") -> dict:
	"""Send a PDF or an image to Gemini and return the cleaned reading (throws a readable error)."""
	key, model = pdf_ocr._settings()
	if not key:
		frappe.throw(_("No Gemini key is set up: add it in Gmail Settings."))
	if not raw or len(raw) > MAX_BYTES:
		frappe.throw(_("The file is empty or larger than 15 MB."))
	if raw[:4] == b"%PDF":
		mime = "application/pdf"
	else:
		try:
			raw, mime = photo_reader.prepare_image(raw)
		except Exception:
			frappe.throw(_("Only PDF files and pictures can be read."))
	body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}},
	                                 {"text": rules.PROMPT}]}],
	        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": rules.SCHEMA}}
	r, error = photo_reader._post(pdf_ocr.ENDPOINT.format(model=model),
	                              {"x-goog-api-key": key, "Content-Type": "application/json"}, body, timeout=180)
	if r is None:
		frappe.log_error(message="Model %s. %s" % (model, error), title="Document reader: Gemini read failed")
		frappe.throw(_("Gemini could not read the file. Try again in a minute.") + " (%s)" % error[:150])
	try:
		out = rules.clean(json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]))
	except Exception:
		frappe.log_error(message="Model %s. Unreadable answer: %s" % (model, r.text[:500]), title="Document reader: bad answer")
		frappe.throw(_("Gemini sent an answer that could not be understood. Try again."))
	if not out["text"] and not out["tables"]:
		frappe.throw(_("Nothing readable was found in the file."))
	out["filename"] = filename
	out["engine"] = "Gemini (%s)" % model
	return out


@frappe.whitelist()
def status():
	_check()
	return {"gemini": bool(pdf_ocr._settings()[0])}


def _own(name: str):
	doc = frappe.get_doc("Document Reading", name)
	if doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _run(name: str):
	"""Background worker: read the file (trying again when Google is busy), keep the result on the record."""
	import time

	doc = frappe.get_doc("Document Reading", name)
	doc.db_set({"status": "Reading", "started_on": frappe.utils.now_datetime(), "error": "", "attempts": 0})
	frappe.db.commit()
	error = ""
	for attempt in range(rules.MAX_ATTEMPTS):
		doc.db_set("attempts", attempt + 1)
		frappe.db.commit()
		try:
			f = frappe.get_doc("File", {"file_url": doc.file_url})
			data = read_bytes(f.get_content(), doc.file_name or "")
			doc.db_set({"status": "Done", "result": json.dumps(data, ensure_ascii=False), "error": "",
			            "finished_on": frappe.utils.now_datetime()})
			frappe.db.commit()
			return
		except Exception as e:
			frappe.db.rollback()
			error = (str(e) or type(e).__name__)[:400]
		if attempt < len(rules.RETRY_WAIT):
			time.sleep(rules.RETRY_WAIT[attempt])
	doc.db_set({"status": "Failed", "error": error, "finished_on": frappe.utils.now_datetime()})
	frappe.db.commit()


def _enqueue(name: str):
	frappe.enqueue("happy_kitchen.recipe_management.document_reader._run", queue="long", timeout=900, name=name)


@frappe.whitelist()
def submit(file_url: str):
	"""Put an uploaded File on the reading list; it is read in the background. Returns the record name."""
	_check()
	f = frappe.get_doc("File", {"file_url": file_url})
	f.check_permission("read")
	doc = frappe.get_doc({"doctype": "Document Reading", "file_url": file_url, "file_name": f.file_name or "", "status": "Queued"})
	doc.insert()
	frappe.db.commit()
	_enqueue(doc.name)
	return doc.name


@frappe.whitelist()
def list_jobs():
	"""The caller's reads, newest first. A read stuck in Reading (worker lost) is marked Failed here."""
	_check()
	rows = frappe.get_all("Document Reading", filters={"owner": frappe.session.user},
	                      fields=["name", "file_name", "status", "attempts", "error", "creation", "started_on", "finished_on"],
	                      order_by="creation desc", limit=50)
	now = frappe.utils.now_datetime().timestamp()
	for r in rows:
		if rules.is_stale(r.status, r.started_on.timestamp() if r.started_on else None, now):
			frappe.db.set_value("Document Reading", r.name, {"status": "Failed", "error": "The reading stopped unexpectedly."})
			r.status, r.error = "Failed", "The reading stopped unexpectedly."
	return rows


@frappe.whitelist()
def get_job(name: str):
	_check()
	doc = _own(name)
	out = {"name": doc.name, "status": doc.status, "error": doc.error, "file_name": doc.file_name}
	if doc.status == "Done" and doc.result:
		out["data"] = json.loads(doc.result)
	return out


@frappe.whitelist()
def retry(name: str):
	_check()
	doc = _own(name)
	if doc.status not in ("Failed", "Done"):
		frappe.throw(_("This file is already being read."))
	doc.db_set({"status": "Queued", "error": ""})
	frappe.db.commit()
	_enqueue(doc.name)


@frappe.whitelist()
def remove(name: str):
	_check()
	_own(name)
	frappe.delete_doc("Document Reading", name, ignore_permissions=True)


def clean_old():
	"""Daily: delete reads (and their uploaded files) older than 30 days."""
	now = frappe.utils.now_datetime().timestamp()
	for r in frappe.get_all("Document Reading", fields=["name", "creation", "file_url"]):
		if rules.is_expired(r.creation.timestamp(), now):
			frappe.delete_doc("Document Reading", r.name, ignore_permissions=True)
			for fname in frappe.get_all("File", filters={"file_url": r.file_url}, pluck="name"):
				frappe.delete_doc("File", fname, ignore_permissions=True)


@frappe.whitelist()
def export_xlsx(data):
	"""The tables as one Excel workbook (one sheet per table, the text on its own sheet). Returns base64."""
	_check()
	d = rules.clean(frappe.parse_json(data) or {})
	sheets = []
	if d["text"]:
		sheets.append(("Text", [[ln] for ln in d["text"].split("\n")]))
	for i, t in enumerate(d["tables"], 1):
		sheets.append(("Table %d" % i, rules.grid(t)))
	if not sheets:
		frappe.throw(_("Nothing to export"))
	import io

	from openpyxl import Workbook

	wb = Workbook()
	wb.remove(wb.active)
	for name, rows in sheets:
		ws = wb.create_sheet(name)
		for row in rows:
			ws.append(row)
	out = io.BytesIO()
	wb.save(out)
	return base64.b64encode(out.getvalue()).decode()
