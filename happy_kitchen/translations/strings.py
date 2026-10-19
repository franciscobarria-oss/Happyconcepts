"""Every user-facing English string in the happy_kitchen app, for the zh-TW list.

Pure Python (no frappe), so tests/test_translations.py can check that each string is
either translated in zh_tw_source.ZH_TW or deliberately left to ERPNext's own
translation (zh_tw_source.LEAVE_AS_IS).

Sources:
- DocType, Report, Page, Workspace, Workspace Sidebar and Desktop Icon JSON:
  names, labels, titles, descriptions, Select options and workspace text blocks.
- Custom fields defined in patches (``"label": ...`` / ``"description": ...``).
- __("...") in JS / HTML and _("...") in Python and Jinja.
"""

from __future__ import annotations

import html
import json
import os
import re

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# folders that hold no user-facing text (test data, translations themselves)
SKIP_DIRS = {"e2e", "translations", "__pycache__", "node_modules"}

_STR = r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\''
JS_CALL = re.compile(r"(?<![\w$.])__\(\s*(?:" + _STR + r"|`([^`$\\]*)`)")
PY_CALL = re.compile(r"(?<![\w.])(?:frappe\.)?_\(\s*(?:" + _STR + r")")
PY_FIELD = re.compile(r'"(?:label|description)":\s*"((?:[^"\\\n]|\\.)*)"')

JSON_KEYS = ("label", "title", "description")
NAMED_DOCTYPES = ("DocType", "Report", "Page", "Workspace", "Workspace Sidebar", "Desktop Icon")
TEXT_BLOCKS = ("header", "paragraph")
TAG = re.compile(r"<[^>]+>")


def _unescape(s: str) -> str:
	return re.sub(r"\\(.)", r"\1", s)


NAMING_SERIES = re.compile(r"\.#+$|\.YYYY\.")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")  # page routes such as stock-take-count


def _clean(s) -> str | None:
	if not isinstance(s, str):
		return None
	s = s.strip()
	if not s or not re.search(r"[A-Za-z]", s) or NAMING_SERIES.search(s) or SLUG.match(s):
		return None
	return s


def strings_from_js(text: str) -> set[str]:
	out = set()
	for m in JS_CALL.finditer(text):
		g = next((g for g in m.groups() if g is not None), "")
		s = _clean(_unescape(g))
		if s:
			out.add(s)
	return out


def strings_from_py(text: str) -> set[str]:
	out = set()
	for m in PY_CALL.finditer(text):
		g = m.group(1) if m.group(1) is not None else m.group(2)
		s = _clean(_unescape(g or ""))
		if s:
			out.add(s)
	return out


def strings_from_py_fields(text: str) -> set[str]:
	return {s for s in (_clean(_unescape(m.group(1))) for m in PY_FIELD.finditer(text)) if s}


def _workspace_text(content: str) -> set[str]:
	out = set()
	try:
		blocks = json.loads(content or "[]")
	except ValueError:
		return out
	for b in blocks:
		if b.get("type") in TEXT_BLOCKS:
			s = _clean(html.unescape(TAG.sub("", (b.get("data") or {}).get("text") or "")))
			if s:
				out.add(s)
	return out


def strings_from_json(doc) -> set[str]:
	"""Labels and names from one exported document (any nesting)."""
	out = set()
	if not isinstance(doc, dict):
		return out
	if doc.get("doctype") in NAMED_DOCTYPES:
		name = _clean(doc.get("name"))
		if name:
			out.add(name)
	if doc.get("doctype") == "Workspace":
		out |= _workspace_text(doc.get("content"))

	def walk(node, is_doctype):
		if isinstance(node, dict):
			for key in JSON_KEYS:
				s = _clean(node.get(key))
				if s:
					out.add(s)
			if is_doctype and node.get("fieldtype") == "Select":
				for opt in (node.get("options") or "").split("\n"):
					s = _clean(opt)
					if s:
						out.add(s)
			for v in node.values():
				if isinstance(v, (dict, list)):
					walk(v, is_doctype)
		elif isinstance(node, list):
			for v in node:
				walk(v, is_doctype)

	walk(doc, doc.get("doctype") == "DocType")
	return out


def collect(app_dir: str = APP_DIR) -> set[str]:
	out: set[str] = set()
	for root, dirs, files in os.walk(app_dir):
		dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
		for f in files:
			path = os.path.join(root, f)
			ext = os.path.splitext(f)[1]
			if ext not in (".js", ".html", ".py", ".json"):
				continue
			with open(path, encoding="utf-8") as fh:
				text = fh.read()
			if ext in (".js", ".html"):
				out |= strings_from_js(text)
				out |= strings_from_py(text)  # Jinja {{ _("...") }}
			elif ext == ".py":
				out |= strings_from_py(text)
				if os.path.basename(root) == "patches":
					out |= strings_from_py_fields(text)
			else:
				try:
					out |= strings_from_json(json.loads(text))
				except ValueError:
					pass
	return out


if __name__ == "__main__":
	import sys

	sys.path.insert(0, os.path.dirname(APP_DIR))
	from happy_kitchen.translations.zh_tw_source import LEAVE_AS_IS, ZH_TW

	missing = sorted(s for s in collect() if s not in ZH_TW and s not in LEAVE_AS_IS)
	for s in missing:
		print(s)
	print(f"{len(missing)} strings without a translation", file=sys.stderr)
