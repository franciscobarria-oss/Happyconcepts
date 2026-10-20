"""Pure rules for picking orders out of e-mail (no Frappe import; tests/test_email_orders.py).

gmail_orders.py feeds these a Gmail API message and acts on the result. Nothing here guesses:
a line that is not clearly "<code> | <name> | <qty>" or "<qty> x <name>" / "<name> x <qty>"
goes to `unparsed` for a person to read."""

from __future__ import annotations

import base64
import html
import re
from email.utils import parseaddr

NUM = r"\d+(?:\.\d+)?"
QTY_FIRST = re.compile(rf"^(?P<qty>{NUM})\s*(?:[x×*]\s+|(?:pcs?|pieces?|boxes|box|kg|g)\s+(?:of\s+)?)(?P<rest>.+)$", re.I)
QTY_LAST = re.compile(rf"^(?P<rest>.+?)\s*(?:[x×*]\s*)(?P<qty>{NUM})\s*(?:pcs?|pieces?|boxes|box|kg|g)?$", re.I)
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,31}$")
HEADER_WORDS = {"qty", "quantity", "code", "sku", "item", "product", "description", "name"}
MAX_BODY = 20000
MAX_PDFS = 8
MAX_PDF_TEXT = 20000
MAX_CELL = 300


def header(payload: dict, name: str) -> str:
	for h in (payload or {}).get("headers") or []:
		if (h.get("name") or "").lower() == name.lower():
			return h.get("value") or ""
	return ""


def parse_sender(value: str) -> tuple[str, str]:
	"""'"Cafe A" <a@x.com>' -> ('Cafe A', 'a@x.com')."""
	name, addr = parseaddr(value or "")
	return name.strip(), addr.strip().lower()


def sender_allowed(address: str, allowed: str | None) -> bool:
	"""`allowed` is a comma / space / line separated list of addresses or @domains; blank = everyone."""
	entries = [e.strip().lower() for e in re.split(r"[,\s;]+", allowed or "") if e.strip()]
	if not entries:
		return True
	address = (address or "").lower()
	return any(address == e or (e.startswith("@") and address.endswith(e)) for e in entries)


def _b64(data: str) -> str:
	if not data:
		return ""
	return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _strip_html(text: str) -> str:
	text = re.sub(r"(?is)<(script|style).*?</\\1>", " ", text)
	text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text)
	text = re.sub(r"(?i)</t[dh]>", " | ", text)
	return html.unescape(re.sub(r"<[^>]+>", " ", text))


QUOTE_START = re.compile(
	r"^(on .{5,200} wrote:|-{2,}\s*(original message|forwarded message)\s*-{2,}|_{5,}|from:\s.+|sent from my .+)$", re.I)


def strip_quoted(text: str) -> str:
	"""A reply's own words only: drop "> quoted" lines and everything after "On ... wrote:" or
	"-----Original Message-----", so the earlier order is not read again as part of the new one."""
	out = []
	for line in (text or "").split("\n"):
		s = line.strip()
		if QUOTE_START.match(s):
			break
		if s.startswith(">"):
			continue
		out.append(line)
	return "\n".join(out)


def body_text(payload: dict) -> str:
	"""Plain text of a Gmail message payload: the text/plain part, else the HTML part stripped."""
	plain, rich = [], []

	def walk(part):
		mime = (part.get("mimeType") or "").lower()
		data = (part.get("body") or {}).get("data")
		if mime == "text/plain" and data:
			plain.append(_b64(data))
		elif mime == "text/html" and data:
			rich.append(_strip_html(_b64(data)))
		for sub in part.get("parts") or []:
			walk(sub)

	walk(payload or {})
	text = strip_quoted("\n".join(plain) if plain else "\n".join(rich))
	lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in text.replace("\r", "").split("\n")]
	return "\n".join(l for l in lines if l)[:MAX_BODY]


def pdf_attachments(payload: dict) -> list[dict]:
	"""PDF attachments of a Gmail message payload: [{filename, attachment_id, data}] (data only when
	Gmail sent the bytes inline, otherwise fetch by attachment_id)."""
	out = []

	def walk(part):
		name = part.get("filename") or ""
		mime = (part.get("mimeType") or "").lower()
		body = part.get("body") or {}
		if (mime == "application/pdf" or name.lower().endswith(".pdf")) and (body.get("attachmentId") or body.get("data")):
			out.append({"filename": name or "order.pdf", "attachment_id": body.get("attachmentId"), "data": body.get("data")})
		for sub in part.get("parts") or []:
			walk(sub)

	walk(payload or {})
	return out[:MAX_PDFS]


QTY_HEADS = ("qty", "quantity", "qnty", "order qty", "ordered", "pcs", "數量", "数量")
CODE_HEADS = ("code", "sku", "item code", "item no", "item no.", "product code", "article", "ref", "編號", "货号", "貨號")
DESC_HEADS = ("description", "item", "product", "item name", "product name", "name", "品名", "名稱", "描述")


def _split_cell(cell, n: int) -> list[str]:
	"""One table cell that holds `n` values (several order lines merged into one row): by line when it
	has `n` lines, else by spaces when it has `n` words; a cell that cannot be split is repeated."""
	text = str(cell or "").strip()
	by_line = [p.strip() for p in text.split("\n") if p.strip()]
	if len(by_line) == n:
		return by_line
	words = text.split()
	if len(words) == n:
		return words
	return [re.sub(r"\s+", " ", text)] * n


def table_to_lines(rows: list[list]) -> list[str]:
	"""Rows of a PDF table -> "CODE | Description | Qty" lines for parse_lines. The header row (the
	first that has a quantity column and a description or code column) says which column is which;
	rows before it, rows without a positive number in the quantity column and total rows are skipped.
	A row that merges several order lines (its quantity cell holds several numbers) is split."""
	head = None
	out = []
	for row in rows or []:
		raw = [str(c or "") for c in row]
		if any(len(c) > MAX_CELL for c in raw):
			continue  # a cell with a whole page of text is not a table row
		cells = [re.sub(r"\s+", " ", c).strip() for c in raw]
		low = [c.lower().rstrip(":") for c in cells]
		if head is None:
			qty = next((i for i, c in enumerate(low) if c in QTY_HEADS), None)
			desc = next((i for i, c in enumerate(low) if c in DESC_HEADS), None)
			code = next((i for i, c in enumerate(low) if c in CODE_HEADS), None)
			if qty is not None and (desc is not None or code is not None):
				head = (code, desc, qty)
			continue
		code, desc, qty = head
		if qty >= len(cells):
			continue
		qty_text = cells[qty].replace(",", "")
		if not re.fullmatch(rf"(?:{NUM}\s*[^\W\d_]*\s*)+", qty_text):
			continue
		nums = re.findall(NUM, qty_text)
		k = len(nums)
		names = _split_cell(raw[desc], k) if desc is not None and desc < len(raw) else [""] * k
		skus = _split_cell(raw[code], k) if code is not None and code < len(raw) else [""] * k
		for name, sku, q in zip(names, skus, nums):
			n = float(q)
			if n <= 0 or not (name or sku) or "total" in (name + sku).lower():
				continue
			out.append(f"{sku} | {name or sku} | {q}" if sku else f"{name} | {q}")
	return out


TEXT_ITEM = re.compile(
	rf"^(?P<desc>.+?)\s+(?P<code>\d{{6,12}})\s+(?P<qty>{NUM})\s+(?P<unit>[^\W\d_]+)\s+(?P<price>[\d,]+\.\d+)\s+(?P<amount>[\d,]+\.\d+)\s*$")


TEXT_ITEM_NOCODE = re.compile(
	rf"^(?P<desc>[^\d].*?)\s+(?P<qty>{NUM})\s+(?P<unit>[^\W\d_]+)\s+(?P<price>[\d,]+\.\d+)\s+(?P<amount>[\d,]+\.\d+)(?:\s+\S+)?\s*$")


def text_item_lines(text: str) -> list[str]:
	"""Order lines from a PDF whose items are plain positioned text, one per line, as
	"description  item-no  qty  unit  unit-price  amount" with the description wrapping onto the
	following line(s). Only read after a header line that has both "Description" and "Quantity", and
	until a "Total" line."""
	out = []
	reading = False
	for raw in (text or "").split("\n"):
		line = re.sub(r"\s+", " ", raw).strip()
		low = line.lower()
		if not reading:
			reading = "description" in low and "quantity" in low
			continue
		if low.startswith("total"):
			reading = False
			continue
		m = TEXT_ITEM.match(line)
		if m:
			out.append([m.group("code"), m.group("desc").strip(), m.group("qty")])
			continue
		m = TEXT_ITEM_NOCODE.match(line)
		if m:
			out.append(["", m.group("desc").strip(), m.group("qty")])
		elif out and line and not re.search(r"\d{1,3}(,\d{3})*\.\d{2}\b", line):
			out[-1][1] = f"{out[-1][1]} {line}"
	return [f"{c} | {d} | {q}" if c else f"{d} | {q}" for c, d, q in out if float(q) > 0]


def drop_repeats(lines: list[str]) -> list[str]:
	"""A PO printed twice in one PDF (page 2 repeats page 1) is read once: identical lines in the
	same PDF are dropped, the first one kept."""
	seen, out = set(), []
	for line in lines:
		if line not in seen:
			seen.add(line)
			out.append(line)
	return out


def join_attachment_text(body: str, texts: list[tuple[str, str]]) -> str:
	"""The email body followed by each PDF's text under a "--- Attachment: name ---" line, so the
	same line reader handles both. Each PDF is capped; an empty PDF (a scan) adds only the header."""
	parts = [body] if body else []
	for name, text in texts:
		parts.append(f"--- Attachment: {name} ---")
		lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in (text or "").replace("\r", "").split("\n")]
		parts.append("\n".join(l for l in lines if l)[:MAX_PDF_TEXT])
	return "\n".join(parts)


def _number(text: str) -> float | None:
	m = re.search(NUM, text or "")
	return float(m.group()) if m else None


def _split_code(rest: str) -> tuple[str, str]:
	"""'CK-001 - Butter cookie' / '[CK-001] Butter cookie' -> ('CK-001', 'Butter cookie'); no code -> ('', rest)."""
	rest = rest.strip()
	m = re.match(r"^\[([^\]]{2,32})\]\s*(.+)$", rest)
	if m:
		return m.group(1).strip(), m.group(2).strip()
	m = re.match(r"^(\S+)\s*[-–:]\s+(.+)$", rest)
	if m and CODE_RE.match(m.group(1)) and any(c.isdigit() for c in m.group(1)):
		return m.group(1), m.group(2).strip()
	m = re.match(r"^(\S+)\s+(.+)$", rest)
	if m and CODE_RE.match(m.group(1)) and any(c.isdigit() for c in m.group(1)) and m.group(1).upper() == m.group(1):
		return m.group(1), m.group(2).strip()
	return "", rest


def parse_lines(text: str) -> tuple[list[dict], list[str]]:
	"""Order lines [{"external_sku", "description", "qty"}] and the lines that could not be read."""
	lines, unparsed = [], []
	for raw in (text or "").split("\n"):
		line = raw.strip(" \t-•*")
		if not line or len(line) > 200 or re.match(r"(?i)^(sub\s*)?total\b", line):
			continue
		if "|" in line or "\t" in line:
			cols = [c.strip() for c in re.split(r"\||\t", line) if c.strip()]
			if not cols or {c.lower() for c in cols} & HEADER_WORDS and _number(" ".join(cols)) is None:
				continue
			qty = _number(cols[-1]) if len(cols) >= 2 and re.fullmatch(rf"{NUM}\s*[A-Za-z]*", cols[-1]) else None
			if qty and qty > 0:
				cols = cols[:-1]
				code, name = (cols[0], cols[1]) if len(cols) >= 2 else ("", cols[0])
				lines.append({"external_sku": code, "description": name, "qty": qty})
				continue
			unparsed.append(raw.strip())
			continue
		m = QTY_FIRST.match(line)
		if m:
			qty, rest = float(m.group("qty")), m.group("rest")
		else:
			m = QTY_LAST.match(line)
			if not m:
				continue  # chatter ("Hi", "Thanks"): only lines that look like an order line count
			qty, rest = float(m.group("qty")), m.group("rest")
		if qty <= 0:
			unparsed.append(raw.strip())
			continue
		code, name = _split_code(rest)
		lines.append({"external_sku": code, "description": name, "qty": qty})
	return lines, unparsed
