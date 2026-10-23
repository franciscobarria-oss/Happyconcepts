"""Custom HTML Blocks kept as files in happy_kitchen/blocks/ and upserted on every migrate
(hooks.after_migrate), so their code lives in git rather than only in the database.
A block named in BLOCKS is overwritten from its files: edit the files, never the record."""

import frappe

from happy_kitchen.setup.block_files import needs_update, read_block

BLOCKS = {
	# "Block Name": "file_stem",  (files: blocks/file_stem.html / .js / .css)
	"HK Team Today": "team_today",
	"HK Team Roster": "team_roster",
	"HK Clock In": "clock_in",
	"HK Today": "today",
	"HK Sales": "sales",
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


# Standard workspaces that get one of our blocks on top: {"Workspace": ("Block Name", "block id")}.
# Re-applied on every migrate, so an ERPNext update that re-imports the workspace keeps it.
ON_TOP = {
	"Selling": ("HK Sales", "hk-sales"),
}


def place():
	from happy_kitchen.setup.workspace_content import with_block_on_top

	for workspace, (block, block_id) in ON_TOP.items():
		if not frappe.db.exists("Workspace", workspace) or not frappe.db.exists("Custom HTML Block", block):
			continue
		doc = frappe.get_doc("Workspace", workspace)
		content = with_block_on_top(doc.content, block, block_id)
		listed = any(r.custom_block_name == block for r in doc.get("custom_blocks") or [])
		if content == doc.content and listed:
			continue
		doc.content = content
		if not listed:
			doc.append("custom_blocks", {"custom_block_name": block, "label": block})
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)
	frappe.db.commit()
