"""Idempotent load of recipes exported from staging (export_recipes.py) into hcl-erp.

Inputs (copy both to /tmp in the hcl-erp backend container):
  - staging_recipes.json   from export_recipes.py
  - code_map.json          {"map": {old_code: new_code | "SKIP"}, "names": {old_code: old item name}}
                           built from approved_matches.json "choices" + new_item_codes.json (+ the merges)

Usage (bench --site hcl-erp.fbs-host.com console):
    exec(open("/tmp/import_recipes.py").read(), globals())
    run("/tmp/staging_recipes.json", "/tmp/code_map.json", dry_run=True)    # everything rolled back
    run("/tmp/staging_recipes.json", "/tmp/code_map.json", dry_run=False)   # commit

Rules:
  - Quantities are copied exactly (never rounded). No precision is set anywhere.
  - Ingredient code: staging product codes stay the same; mapped old codes use the map;
    otherwise an exact (case-insensitive) item-name match on hcl-erp; otherwise "unmatched".
  - A recipe with an unmatched ingredient or a unit that doesn't fit its ingredient is NOT loaded;
    it goes on the review list. Nothing is guessed.
  - Recipe product Items missing on hcl-erp are created with the staging code, name, group and unit.
  - Existing recipes on hcl-erp are left alone (update=True replaces their lines and fields).
  - Sub-recipes (batch preparations, components) load before the recipes that use them.
  - Review CSV written next to the input: recipe_load_review.csv
"""
import csv
import json
import os
import re

import frappe

from happy_kitchen.recipe_management import costing

SUB_TYPES = ("Batch Preparation", "Recipe Component")


def _norm(s):
	return re.sub(r"[^0-9a-z一-鿿]+", " ", (s or "").lower()).strip()


def _ensure_uom(name):
	if name and not frappe.db.exists("UOM", name):
		frappe.get_doc({"doctype": "UOM", "uom_name": name}).insert(ignore_permissions=True)


def _ensure_group(name, groups):
	if not name or frappe.db.exists("Item Group", name):
		return name
	parent = groups.get(name) or "All Item Groups"
	if not frappe.db.exists("Item Group", parent):
		parent = _ensure_group(parent, groups) if parent in groups else "All Item Groups"
	frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent,
	                "is_group": 0}).insert(ignore_permissions=True)
	return name


def _warehouse(staging_wh, company):
	if not staging_wh:
		return None
	base = re.sub(r"\s+-\s+[^-]+$", "", staging_wh)
	return frappe.db.get_value("Warehouse", {"warehouse_name": base, "company": company}, "name")


def _ensure_product(code, it, groups, company):
	if frappe.db.exists("Item", code):
		return False
	_ensure_uom(it["stock_uom"])
	doc = frappe.get_doc({
		"doctype": "Item", "item_code": code, "item_name": it["item_name"],
		"item_group": _ensure_group(it["item_group"], groups) or "Products",
		"stock_uom": it["stock_uom"], "is_stock_item": it["is_stock_item"], "is_sales_item": it["is_sales_item"],
		"is_purchase_item": it["is_purchase_item"], "weight_per_unit": it.get("weight_per_unit") or 0,
		"weight_uom": it.get("weight_uom") or None,
		"description": (it.get("description") or it["item_name"]) + "\nLoaded from staging recipes.",
	})
	for u in it.get("uoms") or []:
		if u["uom"] != it["stock_uom"]:
			_ensure_uom(u["uom"])
			doc.append("uoms", {"uom": u["uom"], "conversion_factor": u["conversion_factor"]})
	wh = _warehouse(it.get("default_warehouse"), company)
	if company:
		doc.append("item_defaults", {"company": company, "default_warehouse": wh})
	doc.insert(ignore_permissions=True)
	return True


def _order(recipes, product_codes):
	"""Sub-recipes first (depth-first on ingredient links to other recipes)."""
	by_item = {r["item"]: r for r in recipes}
	done, out = set(), []

	def visit(r, stack=()):
		if r["item"] in done or r["item"] in stack:
			return
		for line in r["ingredients"]:
			if line["item"] in by_item and line["item"] != r["item"]:
				visit(by_item[line["item"]], stack + (r["item"],))
		done.add(r["item"])
		out.append(r)

	for r in recipes:
		visit(r)
	return out


def resolve_lines(r, data, cmap, names, product_codes):
	"""-> (lines, problems). lines carry the hcl-erp item code."""
	lines, problems = [], []
	for i, l in enumerate(r["ingredients"], 1):
		old = l["item"]
		old_name = (data["items"].get(old) or {}).get("item_name") or l.get("item_name") or ""
		new, how = None, ""
		if old in product_codes:
			new, how = old, "recipe product"
		elif old in cmap and cmap[old] not in ("SKIP", "NEW", ""):
			new, how = cmap[old], "map"
			if names.get(old) and _norm(names[old]) != _norm(old_name):
				problems.append(f"line {i}: {old} is '{old_name}' on staging but '{names[old]}' in the matching list")
		elif old in cmap and cmap[old] == "SKIP":
			problems.append(f"line {i}: {old} {old_name} was marked 'not needed'")
			continue
		if not new:
			hit = frappe.db.sql("select name from tabItem where lower(item_name)=lower(%s) and disabled=0 limit 2", old_name)
			if len(hit) == 1:
				new, how = hit[0][0], "same name"
		if not new or (how != "recipe product" and not frappe.db.exists("Item", new)):
			problems.append(f"line {i}: UNMATCHED {old} {old_name}")
			continue
		if how != "recipe product":
			it = frappe.db.get_value("Item", new, ["stock_uom", "weight_per_unit", "weight_uom", "item_name"], as_dict=True)
			gpp = costing.grams_per_piece(it.weight_per_unit, it.weight_uom)
			try:
				costing.check_uom_compatible(l["uom"], it.stock_uom, gpp)
			except costing.CostingError:
				problems.append(f"line {i}: UNIT {l['qty']} {l['uom']} of {old} {old_name} -> {new} {it.item_name} "
				                f"is stocked in {it.stock_uom} with no weight per piece")
				continue
		lines.append({**l, "item": new, "_old": old, "_how": how})
	return lines, problems


def _supplier(name):
	if not name:
		return None
	return frappe.db.get_value("Supplier", name, "name") or frappe.db.get_value("Supplier", {"supplier_name": name}, "name")


def _fill(doc, r, lines):
	for f in ("recipe_name", "recipe_type", "status", "batch_yield", "yield_uom", "unit_weight"):
		doc.set(f, r.get(f))
	if r.get("selling_price"):
		doc.selling_price = r["selling_price"]
	doc.notes = ((r.get("notes") or "").strip() + f"\nLoaded from staging recipe {r['name']}.").strip()
	doc.set("ingredients", [])
	for l in lines:
		doc.append("ingredients", {"item": l["item"], "qty": l["qty"], "uom": l["uom"], "yield_pct": l.get("yield_pct"),
		                           "supplier": _supplier(l.get("supplier")), "notes": l.get("notes")})
	for t in ("labour", "overheads", "utensils", "steps"):
		doc.set(t, [])
		for row in r.get(t) or []:
			doc.append(t, row)


def run(recipes_path, map_path, dry_run=True, update=False):
	data = json.load(open(recipes_path, encoding="utf-8"))
	m = json.load(open(map_path, encoding="utf-8"))
	cmap, names = m.get("map", m), m.get("names", {})
	company = frappe.defaults.get_global_default("company")
	recipes = data["recipes"]
	product_codes = {r["item"] for r in recipes}
	frappe.flags.in_import = True
	frappe.flags.mute_emails = True

	stats = {"loaded": 0, "updated": 0, "exists": 0, "blocked": 0, "error": 0, "items_created": 0}
	review = []
	blocked_items = set()
	for r in _order(recipes, product_codes):
		lines, problems = resolve_lines(r, data, cmap, names, product_codes)
		# a recipe that uses a blocked sub-recipe is blocked too
		for l in lines:
			if l["item"] in blocked_items:
				problems.append(f"uses sub-recipe {l['item']}, which is not loaded")
		hard = [p for p in problems if "UNMATCHED" in p or "UNIT" in p or "not loaded" in p or "not needed" in p]
		row = {"staging_recipe": r["name"], "item": r["item"], "recipe_name": r["recipe_name"], "type": r["recipe_type"],
		       "status": r["status"], "lines": len(r["ingredients"]), "staging_cost_per_unit": r.get("cost_per_unit"),
		       "result": "", "hcl_cost_per_unit": "", "missing_prices": "", "problems": " | ".join(problems)}
		if hard:
			stats["blocked"] += 1
			blocked_items.add(r["item"])
			row["result"] = "not loaded"
			review.append(row)
			continue
		exists = frappe.db.exists("Recipe", r["item"])
		if exists and not update:
			stats["exists"] += 1
			row["result"] = "already on hcl-erp (left alone)"
			review.append(row)
			continue
		frappe.db.savepoint("hk_recipe")
		try:
			stats["items_created"] += _ensure_product(r["item"], data["items"][r["item"]], data["item_groups"], company)
			doc = frappe.get_doc("Recipe", exists) if exists else frappe.new_doc("Recipe")
			if not exists:
				doc.item = r["item"]
			_fill(doc, r, lines)
			doc.flags.ignore_permissions = True
			doc.save() if exists else doc.insert()
			stats["updated" if exists else "loaded"] += 1
			row["result"] = "updated" if exists else "loaded"
			row["hcl_cost_per_unit"] = doc.cost_per_unit
			row["missing_prices"] = doc.missing_price_count
		except Exception as e:
			frappe.db.rollback(save_point="hk_recipe")
			stats["error"] += 1
			blocked_items.add(r["item"])
			row["result"] = "error"
			row["problems"] = (row["problems"] + " | " if row["problems"] else "") + f"{type(e).__name__}: {e}"[:300]
		review.append(row)

	out = os.path.join(os.path.dirname(recipes_path), "recipe_load_review.csv")
	with open(out, "w", newline="", encoding="utf-8-sig") as f:
		w = csv.DictWriter(f, fieldnames=list(review[0].keys()) if review else ["staging_recipe"])
		w.writeheader()
		w.writerows(review)
	print(stats)
	print("review:", out)
	if dry_run:
		frappe.db.rollback()
		print("DRY RUN, nothing saved")
	else:
		frappe.db.commit()
		print("committed")
	return stats
