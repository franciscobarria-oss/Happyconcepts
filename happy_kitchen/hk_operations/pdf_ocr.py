"""Read a scanned PDF (no text layer) purchase order with the Gemini API.

Only used when pdfplumber finds no text at all. The model returns JSON; it is turned into the same
"--- PO x | date ---" / "CODE | Description | Qty | @ price" lines the table reader makes, plus one
marker line that cannot be parsed, so the Email Order lands in "Needs review" and a person checks the
order against the PDF before it is confirmed. Never raises: no key, no network or a bad answer gives ''."""
from __future__ import annotations

import base64
import json
import re

from happy_kitchen.hk_operations import email_orders

MAX_BYTES = 15 * 1024 * 1024
DEFAULT_MODEL = "gemini-flash-latest"
# Google stopped serving these to new keys (404); a setting saved with one of them uses the default instead.
RETIRED_MODELS = {"gemini-2.5-flash"}
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_WAIT = (5, 20)
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MARKER = "OCR | read by Gemini from a scan: check every line against the PDF"

PROMPT = (
	"This PDF is a scanned customer purchase order for a food supplier. Read every order line. Return JSON only. "
	"Group lines by purchase order number (one PDF can hold several). Use the printed delivery / receipt date as "
	"YYYY-MM-DD, or an empty string if there is none. Copy product codes and descriptions exactly as printed. "
	"qty is the ordered quantity, unit_price the price per unit (0 if not printed). Never guess a value you cannot read: "
	"leave the line out instead. Ignore totals, addresses and terms.")

SCHEMA = {
	"type": "OBJECT",
	"properties": {"orders": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
		"po_number": {"type": "STRING"}, "delivery_date": {"type": "STRING"},
		"lines": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
			"code": {"type": "STRING"}, "description": {"type": "STRING"},
			"qty": {"type": "NUMBER"}, "unit_price": {"type": "NUMBER"}},
			"required": ["description", "qty"]}}},
		"required": ["lines"]}}},
	"required": ["orders"],
}


def to_lines(data: dict) -> str:
	"""The reader's text for the JSON the model returned ('' when it holds no usable line)."""
	out = []
	for order in (data or {}).get("orders") or []:
		lines = []
		for ln in order.get("lines") or []:
			try:
				qty = float(ln.get("qty") or 0)
			except (TypeError, ValueError):
				continue
			desc = re.sub(r"\s+", " ", str(ln.get("description") or "")).replace("|", "/").strip()
			code = re.sub(r"\s+", " ", str(ln.get("code") or "")).replace("|", "/").strip()
			if qty <= 0 or not (desc or code):
				continue
			parts = ([code, desc or code] if code else [desc]) + [("%g" % qty)]
			try:
				price = float(ln.get("unit_price") or 0)
			except (TypeError, ValueError):
				price = 0.0
			parts += email_orders.price_col(price)
			lines.append(" | ".join(parts))
		if not lines:
			continue
		po = re.sub(r"[^A-Za-z0-9-]", "", str(order.get("po_number") or "")).upper()
		date = email_orders.parse_date(str(order.get("delivery_date") or ""))
		out += ([f"--- PO {po}{' | ' + date if date else ''} ---"] if po else []) + lines
	return ("\n".join(out + [MARKER])) if out else ""


def _settings():
	import frappe

	s = frappe.get_single("Gmail Settings")
	model = (s.get("gemini_model") or "").strip()
	return s.get_password("gemini_api_key", raise_exception=False), (DEFAULT_MODEL if not model or model in RETIRED_MODELS else model)


def _call(key: str, model: str, raw: bytes):
	"""POST the PDF to Gemini, trying again when Google is busy or slow. Returns (response or None, error text)."""
	import time

	import requests

	body = {"contents": [{"parts": [
		{"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(raw).decode()}},
		{"text": PROMPT}]}],
		"generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA}}
	error = ""
	for attempt in range(len(RETRY_WAIT) + 1):
		try:
			r = requests.post(ENDPOINT.format(model=model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
			                  json=body, timeout=90)
			if r.status_code == 200:
				return r, ""
			error = "HTTP %s: %s" % (r.status_code, r.text[:500])
			if r.status_code not in RETRY_STATUS:
				return None, error
		except requests.RequestException as e:
			error = "%s: %s" % (type(e).__name__, str(e)[:300])
		if attempt < len(RETRY_WAIT):
			time.sleep(RETRY_WAIT[attempt])
	return None, error


def ocr_text(raw: bytes) -> str:
	key, model = _settings()
	if not key or not raw or len(raw) > MAX_BYTES:
		return ""
	import frappe

	r, error = _call(key, model, raw)
	if r is None:
		frappe.log_error(message="Model %s. %s" % (model, error), title="Email order OCR: Gemini read failed")
		return ""
	try:
		text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
		return to_lines(json.loads(text))
	except Exception:
		frappe.log_error(message="Model %s. Unreadable answer: %s" % (model, r.text[:500]), title="Email order OCR: bad answer")
		return ""
