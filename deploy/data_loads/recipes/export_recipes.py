"""Export every Recipe (with its child tables) and the Items it uses from a site, read-only.

Run on the STAGING site (erp-staging), inside its backend container:
    bench --site <staging-site> console   then:
        exec(open("/tmp/export_recipes.py").read(), globals()); run("/tmp/staging_recipes.json")

Writes one JSON file: recipes, the items they reference (products and ingredients),
item groups, and supplier names. Nothing on the site changes.
"""
import json

import frappe

CHILD_FIELDS = {
	"ingredients": ["item", "item_name", "qty", "uom", "yield_pct", "supplier", "notes", "component_type", "stock_uom"],
	"labour": ["activity", "staff_role", "hourly_rate", "minutes"],
	"overheads": ["service", "basis", "rate", "notes"],
	"utensils": ["utensil", "notes"],
	"steps": ["instruction"],
}
RECIPE_FIELDS = ["name", "item", "recipe_name", "recipe_type", "status", "item_group", "batch_yield", "yield_uom",
                 "selling_price", "unit_weight", "notes", "image", "cost_per_unit", "total_batch_cost", "missing_price_count"]
ITEM_FIELDS = ["item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "is_sales_item",
               "is_purchase_item", "weight_per_unit", "weight_uom", "description", "disabled"]


def run(out_path):
	recipes = []
	codes = set()
	for name in frappe.get_all("Recipe", pluck="name", order_by="name"):
		doc = frappe.get_doc("Recipe", name)
		r = {f: doc.get(f) for f in RECIPE_FIELDS}
		for table, fields in CHILD_FIELDS.items():
			r[table] = [{f: row.get(f) for f in fields} for row in doc.get(table) or []]
		codes.add(doc.item)
		codes.update(row["item"] for row in r["ingredients"])
		recipes.append(r)

	items = {}
	for code in sorted(c for c in codes if c):
		it = frappe.db.get_value("Item", code, ITEM_FIELDS, as_dict=True)
		if not it:
			continue
		it["uoms"] = frappe.get_all("UOM Conversion Detail", filters={"parent": code, "parenttype": "Item"},
		                            fields=["uom", "conversion_factor"])
		it["default_warehouse"] = frappe.db.get_value("Item Default", {"parent": code}, "default_warehouse")
		items[code] = it

	groups = {g.name: g.parent_item_group for g in frappe.get_all("Item Group", fields=["name", "parent_item_group"])}
	out = {"site": frappe.local.site, "recipes": recipes, "items": items, "item_groups": groups}
	with open(out_path, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1, default=str)
	from collections import Counter
	print("recipes:", len(recipes), dict(Counter((r["recipe_type"], r["status"]) for r in recipes)))
	print("items referenced:", len(items), "lines:", sum(len(r["ingredients"]) for r in recipes))
	print("written", out_path)
