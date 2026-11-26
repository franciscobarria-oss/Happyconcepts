"""The desk shows exactly ten workspaces (plus Stock Take on its own), in this order. Plain data and
pure rules (unit-tested); `apply()` hides every other standard desktop icon. Re-applied on every migrate
because an ERPNext / HRMS update re-imports its own icons. Hidden, never deleted: set site_config
`hk_show_standard_workspaces` to 1 to leave them alone, or untick Hidden on a Desktop Icon."""

# Desktop Icon names, in desk order. The first ten are the workspaces Francisco asked for (2026-11-20).
TEN = ["Recipes", "Suppliers", "Sales", "Team", "Clock In", "Kitchen Checks", "Accounting",
       "Recipe Costing", "Reports", "Today"]
OUTSIDE = ["Stock Take"]  # shown after the ten, not one of them
OURS = TEN + OUTSIDE
PAGE_ICONS = ["Document reader"]  # icons that open a page directly (no workspace), shown after Stock Take
# Workspace -> module. Each icon needs its own: the desk finds an icon's sidebar by its workspace's module.
# Frappe skips workspace files whose `modified` did not change, so a module moved in the JSON never reached
# existing sites (Sales kept opening HR); `apply()` sets it on every migrate.
WORKSPACE_MODULE = {
	"Recipes": "Recipe Management", "Suppliers": "HK Suppliers", "Sales": "HK Sales", "Team": "HK Operations",
	"Clock In": "HK Clock In", "Kitchen Checks": "HK Compliance", "Accounting": "HK Accounting",
	"Recipe Costing": "HK Costing", "Reports": "HK Reports", "Today": "HK Today", "Stock Take": "HK Stock Take",
}
# Never hidden: the folder our icons sit in is kept by `to_hide`, these are admin screens.
KEEP = {"Settings", "Users", "Home", "Build", "Integrations"}


def to_hide(icons):
	"""icons: [{"name", "parent_icon", "hidden"}]. Names to hide: every icon that is not ours, not the
	folder one of ours sits in, and not in KEEP. Already hidden ones are left out."""
	parents = {i.get("parent_icon") for i in icons if i["name"] in OURS + PAGE_ICONS and i.get("parent_icon")}
	return [i["name"] for i in icons
	        if i["name"] not in OURS + PAGE_ICONS and i["name"] not in parents and i["name"] not in KEEP and not i.get("hidden")]


def apply():
	import frappe

	if not frappe.db.exists("DocType", "Desktop Icon"):
		return
	if frappe.db.exists("DocType", "Workspace"):
		for name, module in WORKSPACE_MODULE.items():
			if frappe.db.get_value("Workspace", name, "module") not in (None, module) and frappe.db.exists("Module Def", module):
				frappe.db.set_value("Workspace", name, "module", module, update_modified=False)
	if not frappe.conf.get("hk_show_standard_workspaces"):
		icons = frappe.get_all("Desktop Icon", fields=["name", "parent_icon", "hidden"])
		for name in to_hide(icons):
			frappe.db.set_value("Desktop Icon", name, "hidden", 1, update_modified=False)
	frappe.db.commit()
