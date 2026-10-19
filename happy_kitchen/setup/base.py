"""Applies setup/base_data.py to a site. Every step is idempotent: it runs after install,
from the base_setup patch on existing sites, and can be re-run with
`bench --site <site> execute happy_kitchen.setup.base.apply`."""

import frappe

from happy_kitchen.setup import base_data as d


def apply():
	settings()
	uoms()
	company = frappe.defaults.get_global_default("company")
	if company:
		abbr = frappe.db.get_value("Company", company, "abbr")
		warehouses(company, abbr)
	item_groups()
	roles()
	role_profiles()
	hide_desktop_icons()
	frappe.db.commit()
	frappe.clear_cache()


def settings():
	frappe.db.set_single_value("System Settings", "currency_precision", d.CURRENCY_PRECISION)
	frappe.db.set_single_value("System Settings", "enable_onboarding", 0)
	frappe.db.set_single_value("Buying Settings", "maintain_same_rate", 1)
	for lang in d.LANGUAGES_ENABLED:
		if frappe.db.exists("Language", lang):
			frappe.db.set_value("Language", lang, "enabled", 1)


def uoms():
	for name, whole in d.UOMS.items():
		if frappe.db.exists("UOM", name):
			frappe.db.set_value("UOM", name, "must_be_whole_number", whole)
		else:
			frappe.get_doc({"doctype": "UOM", "uom_name": name, "must_be_whole_number": whole}).insert(
				ignore_permissions=True
			)


def warehouses(company, abbr):
	for old, new in d.WAREHOUSE_RENAMES.items():
		old_name, new_name = d.with_abbr(old, abbr), d.with_abbr(new, abbr)
		if frappe.db.exists("Warehouse", old_name) and not frappe.db.exists("Warehouse", new_name):
			frappe.rename_doc("Warehouse", old_name, new_name, force=True)
			frappe.db.set_value("Warehouse", new_name, "warehouse_name", new)
	parent = d.with_abbr("All Warehouses", abbr)
	for name in d.WAREHOUSES:
		if not frappe.db.exists("Warehouse", d.with_abbr(name, abbr)):
			frappe.get_doc({
				"doctype": "Warehouse", "warehouse_name": name, "company": company,
				"parent_warehouse": parent if frappe.db.exists("Warehouse", parent) else None,
			}).insert(ignore_permissions=True)
	frappe.db.set_single_value("Stock Settings", "default_warehouse", d.with_abbr(d.DEFAULT_WAREHOUSE, abbr))


def _item_group(name, parent, is_group):
	if frappe.db.exists("Item Group", name):
		values = {"parent_item_group": parent}
		if is_group and not frappe.db.exists("Item", {"item_group": name}):
			values["is_group"] = 1
		frappe.db.set_value("Item Group", name, values)
	else:
		frappe.get_doc({
			"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent, "is_group": is_group,
		}).insert(ignore_permissions=True)


def item_groups():
	root = "All Item Groups"
	for parent, children in d.ITEM_GROUPS.items():
		_item_group(parent, root, 1)
		for child in children:
			_item_group(child, parent, 0)
	for name in d.LEAF_ITEM_GROUPS:
		_item_group(name, root, 0)
	# set_value bypasses the nested-set update, so rebuild lft/rgt once at the end
	from frappe.utils.nestedset import rebuild_tree

	rebuild_tree("Item Group")


def roles():
	for name, desk in d.ROLES.items():
		if not frappe.db.exists("Role", name):
			frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": desk}).insert(
				ignore_permissions=True
			)


def role_profiles():
	existing = set(frappe.get_all("Role", pluck="name"))
	for profile, wanted in d.ROLE_PROFILES.items():
		if frappe.db.exists("Role Profile", profile):
			continue
		doc = frappe.new_doc("Role Profile")
		doc.role_profile = profile
		for role in wanted:
			if role in existing:
				doc.append("roles", {"role": role})
		doc.insert(ignore_permissions=True)


def hide_desktop_icons():
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return
	for name in d.HIDDEN_DESKTOP_ICONS:
		if frappe.db.exists("Desktop Icon", name):
			frappe.db.set_value("Desktop Icon", name, "hidden", 1)
