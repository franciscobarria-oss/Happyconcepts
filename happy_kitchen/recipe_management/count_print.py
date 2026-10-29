"""Printable A4 count sheet for manual stock taking: every ingredient of a Stock Take
Sheet (or of an existing Stock Take) in counting order, grouped by storage area, with
blank boxes for each pack size and for loose units.

	/api/method/happy_kitchen.recipe_management.count_print.sheet?sheet=Main Kitchen
	/api/method/happy_kitchen.recipe_management.count_print.sheet?take=STK-2026-0002&show_stock=1

show_stock=1 also prints what ERPNext thinks is in stock (off by default, so the count is blind)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, format_datetime, formatdate, getdate, now_datetime, nowdate
from werkzeug.wrappers import Response

from happy_kitchen.recipe_management.doctype.stock_take.stock_take import pack_factor
from happy_kitchen.recipe_management.variance import pack_caption

PACK_FIELDS = ("pack_uom", "pack_uom_2", "pack_uom_3")
LOOSE_LABEL = {"g": "g", "kg": "kg", "ml": "ml", "l": "L", "piece": "pcs"}


def rows_for(sheet: str | None, take: str | None) -> tuple[dict, list[dict]]:
	"""(heading info, one dict per ingredient) from a Stock Take Sheet or a Stock Take."""
	if take:
		doc = frappe.get_doc("Stock Take", take)
		doc.check_permission("read")
		info = {"title": doc.name, "sheet": doc.stock_take_sheet, "date": str(doc.posting_date), "company": doc.company}
		src = [r for r in doc.items]
		get_packs = lambda r: [(r.get(f), r.get(f.replace("pack_uom", "pack_factor"))) for f in PACK_FIELDS if r.get(f)]
	else:
		doc = frappe.get_doc("Stock Take Sheet", sheet)
		doc.check_permission("read")
		info = {"title": doc.name, "sheet": doc.name, "date": "", "company": doc.company}
		src = [r for r in doc.items if r.active]
		get_packs = lambda r: [(r.get(f), None) for f in PACK_FIELDS if r.get(f)]
	out = []
	for r in src:
		stock_uom = frappe.get_cached_value("Item", r.item, "stock_uom")
		packs = []
		for uom, factor in get_packs(r):
			factor = factor or pack_factor(r.item, uom)
			packs.append({"uom": uom, "caption": pack_caption(uom, factor, stock_uom)})
		out.append({
			"item": r.item, "name": r.item_name or frappe.get_cached_value("Item", r.item, "item_name"),
			"area": r.storage_area or "", "packs": packs, "stock_uom": stock_uom,
			"loose": LOOSE_LABEL.get(r.count_uom, r.count_uom or ""),
		})
	return info, out


def group_by_area(rows: list[dict]) -> list[dict]:
	"""One group per storage area (in order of first appearance), rows keeping the sheet's counting order."""
	groups: dict[str, dict] = {}
	for r in rows:
		g = groups.setdefault(r["area"], {"area": r["area"], "label": (r["area"] or "").rsplit(" - ", 1)[0], "rows": []})
		g["rows"].append(r)
	return list(groups.values())


def stock_levels(rows: list[dict]) -> dict[str, float]:
	items = [r["item"] for r in rows]
	out: dict[str, float] = {}
	for b in frappe.get_all("Bin", filters={"item_code": ("in", items or [""])}, fields=["item_code", "warehouse", "actual_qty"]):
		out[(b.item_code, b.warehouse)] = flt(b.actual_qty)
	return out


@frappe.whitelist()
def sheet(sheet: str | None = None, take: str | None = None, show_stock: int | str = 0):
	"""The printable A4 count sheet (HTML)."""
	if not sheet and not take:
		frappe.throw(_("Choose a Stock Take Sheet or a Stock Take."))
	info, rows = rows_for(sheet, take)
	show_stock = cint(show_stock)
	stock = stock_levels(rows) if show_stock else {}
	for r in rows:
		if show_stock:
			q = stock.get((r["item"], r["area"]), 0.0)
			r["system"] = f"{q / 1000:,.2f}".rstrip("0").rstrip(".") + " kg" if r["stock_uom"] == "Gram" and abs(q) >= 1000 else f"{q:,.0f} " + ("g" if r["stock_uom"] == "Gram" else "pcs")
	context = {
		"info": info, "groups": group_by_area(rows), "total": len(rows),
		"pack_cols": max([len(r["packs"]) for r in rows] or [0]),
		"b": frappe.get_attr("happy_kitchen.recipe_management.utils.get_recipe_branding")(),
		"printed": format_datetime(now_datetime(), "dd-MM-yyyy HH:mm"),
		"printed_by": frappe.utils.get_fullname(frappe.session.user),
		"date_fmt": formatdate(info["date"]) if info["date"] else "",
		"show_stock": show_stock, "sheet": sheet, "take": take,
	}
	html = frappe.render_template("happy_kitchen/templates/count_sheet.html", context)
	return Response(html, content_type="text/html; charset=utf-8")
