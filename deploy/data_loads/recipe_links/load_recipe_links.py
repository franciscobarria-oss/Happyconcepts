"""Fill Item.hk_recipe ("Made From Recipe", qty 1) for sold items that are sold under another code than the
recipe's own item. Idempotent: only a blank hk_recipe is filled; an item that already points elsewhere is left
alone and listed. Only Active recipes are linked. Dry run by default.

On the server, in the hcl-erp backend container (copy recipe_links.json to /tmp first):
    bench --site <site> console
    exec(open("/tmp/load_recipe_links.py").read(), globals()); run("/tmp/recipe_links.json")            # dry run
    exec(open("/tmp/load_recipe_links.py").read(), globals()); run("/tmp/recipe_links.json", apply=True)
"""
import json

import frappe


def run(path, apply=False):
	links = json.load(open(path, encoding="utf-8"))
	done, same, clash, no_item, no_recipe = [], [], [], [], []
	for item, recipe in links.items():
		if not frappe.db.exists("Item", item):
			no_item.append(item)
			continue
		if frappe.db.get_value("Recipe", recipe, "status") != "Active":
			no_recipe.append((item, recipe))
			continue
		cur = frappe.db.get_value("Item", item, "hk_recipe")
		if not cur:
			done.append((item, recipe))
			if apply:
				frappe.db.set_value("Item", item, {"hk_recipe": recipe, "hk_recipe_qty": 1}, update_modified=False)
		elif cur == recipe:
			same.append(item)
		else:
			clash.append((item, cur, recipe))
	if apply:
		frappe.db.commit()
	print("APPLIED" if apply else "DRY RUN", "| to link:", len(done), "| already linked:", len(same),
	      "| linked elsewhere (left alone):", len(clash), "| no item:", len(no_item), "| recipe not Active:", len(no_recipe))
	for r in done:
		print("  link", r)
	for r in clash:
		print("  elsewhere", r)
	print("  no item:", no_item, "| recipe not active:", no_recipe)
