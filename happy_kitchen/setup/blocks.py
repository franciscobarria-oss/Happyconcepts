"""Custom HTML Blocks kept as files in happy_kitchen/blocks/ and upserted on every migrate
(hooks.after_migrate), so their code lives in git rather than only in the database.
A block named in BLOCKS is overwritten from its files: edit the files, never the record."""

import frappe

from happy_kitchen.setup.block_files import needs_update, read_block

BLOCKS = {
	# "Block Name": "file_stem",  (files: blocks/file_stem.html / .js / .css)
}


def sync():
	if not BLOCKS or not frappe.db.exists("DocType", "Custom HTML Block"):
		return
	for name, stem in BLOCKS.items():
		values = {**read_block(stem), "private": 0}
		if frappe.db.exists("Custom HTML Block", name):
			doc = frappe.get_doc("Custom HTML Block", name)
			if not needs_update(doc.as_dict(), values):
				continue
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "Custom HTML Block", **values}).insert(
				ignore_permissions=True, set_name=name
			)
	frappe.db.commit()
