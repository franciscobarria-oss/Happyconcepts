"""Puts a Custom HTML Block at the top of a standard (ERPNext) workspace's content
(no Frappe import, so it is unit-tested). Used for "HK Sales" on the Selling workspace."""

import json


def with_block_on_top(content, block_name, block_id, drop_types=("onboarding",)):
	"""The workspace content (JSON text) with the block first, full width, exactly once.
	Blocks of drop_types (the setup onboarding panel) are removed. Returns JSON text."""
	blocks = json.loads(content or "[]")
	kept = [
		b for b in blocks
		if b.get("type") not in drop_types
		and not (b.get("type") == "custom_block" and (b.get("data") or {}).get("custom_block_name") == block_name)
	]
	ours = {"id": block_id, "type": "custom_block", "data": {"custom_block_name": block_name, "col": 12}}
	return json.dumps([ours] + kept)
