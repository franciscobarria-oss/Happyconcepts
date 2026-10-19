"""Replace one ingredient by another in many recipes at once: offered on the
Recipe form after an ingredient is swapped, and on the Item form
("Replace in recipes...")."""

import json

import frappe
from frappe import _
from frappe.utils import flt, strip_html

from happy_kitchen.recipe_management.swap import plan_swap

ARCHIVED = "Archived"


def _recipe_names(item_code: str) -> list[str]:
	return frappe.get_all(
		"Recipe Ingredient", filters={"parenttype": "Recipe", "item": item_code}, pluck="parent", distinct=True, order_by="parent"
	)


@frappe.whitelist()
def recipes_using(item_code: str, exclude: str | None = None) -> dict:
	"""The recipes an ingredient is used in, with its amount in each. Archived
	recipes are only counted: they keep the ingredients they were archived with."""
	if not frappe.has_permission("Recipe", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	names = [n for n in _recipe_names(item_code) if n != exclude]
	if not names:
		return {"recipes": [], "archived": 0}
	recipes = frappe.get_all(
		"Recipe", filters={"name": ("in", names)}, fields=["name", "recipe_name", "status", "recipe_type"], order_by="recipe_name"
	)
	lines = frappe.get_all(
		"Recipe Ingredient",
		filters={"parenttype": "Recipe", "item": item_code, "parent": ("in", names)},
		fields=["parent", "qty", "uom"],
		order_by="idx",
	)
	for r in recipes:
		r["lines"] = [{"qty": l.qty, "uom": l.uom} for l in lines if l.parent == r.name]
	return {
		"recipes": [r for r in recipes if r.status != ARCHIVED],
		"archived": sum(1 for r in recipes if r.status == ARCHIVED),
	}


@frappe.whitelist(methods=["POST"])
def replace_in_recipes(old_item: str, new_item: str, recipes, factor: float = 1, source: str | None = None) -> dict:
	"""Use new_item instead of old_item in the given recipes, with the same
	amount times `factor`. Each recipe is saved (and so re-costed) on its own: one
	that fails validation is reported and left unchanged."""
	if isinstance(recipes, str):
		recipes = json.loads(recipes)
	factor = flt(factor) or 1
	if factor <= 0:
		frappe.throw(_("The quantity factor must be more than 0."))
	if old_item == new_item:
		frappe.throw(_("Choose a different ingredient to replace {0} with.").format(old_item))
	new = frappe.db.get_value("Item", new_item, ["item_name", "disabled"], as_dict=True)
	if not new or new.disabled:
		frappe.throw(_("{0} doesn't exist or is disabled.").format(new_item))
	old_name = frappe.db.get_value("Item", old_item, "item_name") or old_item

	used_in = set(_recipe_names(old_item))
	changed, failed, skipped = [], [], []
	for name in recipes or []:
		if name not in used_in:
			skipped.append({"recipe": name, "reason": _("doesn't use {0}").format(old_name)})
			continue
		doc = frappe.get_doc("Recipe", name)
		if doc.status == ARCHIVED:
			skipped.append({"recipe": name, "reason": _("archived")})
			continue
		if not frappe.has_permission("Recipe", "write", doc):
			skipped.append({"recipe": name, "reason": _("no permission to change it")})
			continue
		frappe.db.savepoint("hk_swap")
		messages = len(frappe.local.message_log)
		try:
			_apply(doc, old_item, new_item, new.item_name, factor)
			doc.save()
			msg = _("{0} replaced by {1}").format(old_name, new.item_name)
			if factor != 1:
				msg += " " + _("(quantity × {0})").format(frappe.format(factor, {"fieldtype": "Float"}))
			if source and source != name:
				msg += " " + _("from recipe {0}").format(source)
			doc.add_comment("Comment", msg)
			changed.append(name)
		except Exception as e:
			frappe.db.rollback(save_point="hk_swap")
			del frappe.local.message_log[messages:]  # reported in the result instead of as pop-ups
			failed.append({"recipe": name, "error": strip_html(str(e)) or _("could not be saved")})
	return {"changed": changed, "failed": failed, "skipped": skipped}


def _apply(doc, old_item: str, new_item: str, new_name: str, factor: float):
	rows = list(doc.ingredients)
	lines = [{"item": r.item, "qty": r.qty, "uom": r.uom, "yield_pct": r.yield_pct} for r in rows]
	drop = []
	for action in plan_swap(lines, old_item, new_item, factor):
		if action[0] == "merge":
			_, i, j, qty = action
			rows[j].qty = flt(rows[j].qty) + qty
			drop.append(rows[i])
		else:
			_, i, qty = action
			row = rows[i]
			row.item, row.item_name, row.qty = new_item, new_name, qty
			row.supplier = row.item_price = row.working_recipe = None  # picked again for the new item on save
	for row in drop:
		doc.remove(row)
	for idx, row in enumerate(doc.ingredients, 1):
		row.idx = idx
