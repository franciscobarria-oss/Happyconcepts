"""Pure rules for the document reader (no frappe): the Gemini request schema, cleaning the answer, CSV / TSV text."""
from __future__ import annotations

import csv
import io

PROMPT = (
	"Read this document like an OCR engine. Return JSON only. "
	"`text` is the full text exactly as printed or written, in reading order, keeping the original language (English and "
	"Chinese), one line per line of the page, with a blank line between paragraphs. Do not summarise, translate or correct. "
	"Leave table content out of `text` and put every table in `tables` instead: `title` (a heading above it, or empty), "
	"`headers` (the header row, or empty strings if there is none) and `rows` (every row, each a list of cell strings, the "
	"same number of cells as headers, merged cells repeated or left empty). Copy numbers, codes and dates exactly as printed. "
	"Never invent text you cannot read: leave it out and add a short note to `unclear`.")

SCHEMA = {
	"type": "OBJECT",
	"properties": {
		"text": {"type": "STRING"},
		"tables": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
			"title": {"type": "STRING"},
			"headers": {"type": "ARRAY", "items": {"type": "STRING"}},
			"rows": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "STRING"}}}},
			"required": ["rows"]}},
		"unclear": {"type": "ARRAY", "items": {"type": "STRING"}},
	},
	"required": ["text", "tables"],
}


def _cell(v) -> str:
	return "" if v is None else str(v).replace("\r", " ").strip()


def clean(data: dict) -> dict:
	"""Tidy the model's answer: strings only, every row as wide as the widest row / header, empty tables dropped."""
	data = data or {}
	tables = []
	for t in data.get("tables") or []:
		headers = [_cell(h) for h in (t.get("headers") or [])]
		rows = [[_cell(c) for c in (r if isinstance(r, list) else [r])] for r in (t.get("rows") or [])]
		rows = [r for r in rows if any(r)]
		if not rows:
			continue
		width = max([len(headers)] + [len(r) for r in rows])
		headers = headers + [""] * (width - len(headers)) if any(headers) else []
		tables.append({"title": _cell(t.get("title")), "headers": headers,
		               "rows": [r + [""] * (width - len(r)) for r in rows]})
	return {"text": str(data.get("text") or "").strip(), "tables": tables,
	        "unclear": [_cell(u) for u in (data.get("unclear") or []) if _cell(u)]}


def grid(table: dict) -> list[list[str]]:
	return ([table["headers"]] if table.get("headers") else []) + list(table.get("rows") or [])


def to_csv(table: dict) -> str:
	"""CSV text; the screen adds a BOM when saving so Excel opens Chinese correctly."""
	out = io.StringIO()
	csv.writer(out, lineterminator="\r\n").writerows(grid(table))
	return out.getvalue()


def to_tsv(table: dict) -> str:
	"""Tab-separated text that pastes into Excel / Sheets as cells."""
	return "\n".join("\t".join(c.replace("\t", " ").replace("\n", " ") for c in row) for row in grid(table))


# Reading queue rules (Document Reading records).
RETRY_WAIT = (60, 180)  # seconds to wait before attempt 2 and 3
MAX_ATTEMPTS = len(RETRY_WAIT) + 1
STALE_AFTER = 30 * 60  # a read still "Reading" after this many seconds lost its worker
KEEP_DAYS = 30


def is_stale(status: str, started_ts: float | None, now_ts: float, limit: int = STALE_AFTER) -> bool:
	return status == "Reading" and started_ts is not None and now_ts - started_ts > limit


def is_expired(created_ts: float, now_ts: float, days: int = KEEP_DAYS) -> bool:
	return now_ts - created_ts > days * 86400
