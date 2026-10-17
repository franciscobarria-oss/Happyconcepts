"""Reads Custom HTML Block sources from happy_kitchen/blocks/ (no Frappe import, so it is unit-tested).

A block is up to three files sharing a stem: <stem>.html, <stem>.js (script) and <stem>.css (style)."""

import os

BLOCKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blocks")

FIELDS = (("html", "html"), ("script", "js"), ("style", "css"))


def read_block(stem, blocks_dir=BLOCKS_DIR):
	values = {}
	for field, ext in FIELDS:
		path = os.path.join(blocks_dir, f"{stem}.{ext}")
		if os.path.exists(path):
			with open(path, encoding="utf-8") as f:
				values[field] = f.read()
		else:
			values[field] = ""
	if not any(values.values()):
		raise FileNotFoundError(f"No block files for '{stem}' in {blocks_dir}")
	return values


def needs_update(current, wanted):
	"""True if any field of the stored block differs from the files (None counts as empty)."""
	return any((current.get(k) or "") != v for k, v in wanted.items())
