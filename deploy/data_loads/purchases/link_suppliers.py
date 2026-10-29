"""Pass 2: link old suppliers (via alias map) to the new items ING-531.. and load old Standard Buying prices.
Idempotent: skips a supplier row / price that already exists. dry_run rolls back."""
import json, re
import frappe

ALIAS = {
	"Unigra Spa": "Unigra SpA",
	"Ongo": "Ongo Food Ltd 安高食材有限公司",
	"Hop Lee Seafood Co. Ltd.": "Hop Lee Seafood Co. Ltd. 合利海鮮有限公司",
	"Man Wui Foods Limited": "Man Wui Foods Ltd 文匯食品有限公司",
	"Foodgears": "Foodgears Industrial International Ltd. 福基國際工業股份有限公司",
	"Angliss": "Angliss Hong Kong Food Service Ltd 安得利香港餐飲有限公司",
	"Bakels": "Bakels Hong Kong Ltd 香港碧琪有限公司",
	"The Garden": "The Garden Company Ltd. 嘉頓有限公司",
	"Taste Charming": "Taste Charming International Trading Limited 味之都",
	"Classic Fine Foods": "Classic Fine Foods (Hong Kong) Ltd.",
	"ETAK International Ltd": "ETAK International Ltd. 意得國際有限公司",
	"The Food Source Ltd": "The Food Source Ltd. 一方食品亞洲有限公司",
	"Tak Shing Cheong": "Tak Shing Cheong Food Ltd. 德成昌食品有限公司",
	"Kingsway": "Kingsway Food International Ltd 健威食品國際有限公司",
	"Century Food": "Century Food Company Ltd",
	"W.E. Food": "W.E. Food Service Company Limited 匯盈食品有限公司",
	"Creative Food": "Creative Foodservice & Packaging Ltd. 創意食品包裝有限公司",
	"Taobao": "Unnamed shop (Taobao)",
	"A&W International Co. Ltd": "A&W International Co. Ltd",  # created below
	"Twinsco": "Twinsco",  # created below
	"Goodwell": "Goodwell",  # created below (Francisco 2026-10-24: "1")
	"You Origin": "You Origin",  # created below (Francisco 2026-10-24: "1")
	"SIMS": "SIMS",  # created below (Francisco 2026-10-24: "1")
	"Kai Fat": "Kai Fat",  # created below (Francisco 2026-10-24: "1")
	"TCI": "TCI",  # created below (Francisco 2026-10-24: "1")
	"Sweet Forest": "Sweet Forest",  # created below (Francisco 2026-10-24: "1")
	"Venki": "Venki",  # created below (Francisco 2026-10-24: "1")
	"Taikoo": "Taikoo",  # created below (Francisco 2026-10-24: "1")
	"Chef's Garden": "Chef's Garden",  # created below
}
CREATE = {"A&W International Co. Ltd": "Trade Supplier", "Twinsco": "Trade Supplier"}
# old system had only name / Company / Hong Kong for these
CREATE.update({n: "Trade Supplier" for n in ['Goodwell', 'You Origin', 'SIMS', 'Kai Fat', 'TCI', 'Sweet Forest', 'Venki', 'Taikoo', "Chef's Garden"]})
COUNTRY = {n: "Hong Kong" for n in ['Goodwell', 'You Origin', 'SIMS', 'Kai Fat', 'TCI', 'Sweet Forest', 'Venki', 'Taikoo', "Chef's Garden"]}
# merged duplicates: their old supplier goes on the kept item as an extra supplier (price per stock unit of the kept item)
EXTRA = {}  # A&W on ING-547: link only - old 0.74/g price has the wrong unit, so no price
# Francisco 2026-10-24: only these old suppliers for now (the other 16 wait for "OK, link the 16")
ACTIVE = set(ALIAS)  # 2026-10-24 Francisco: "ok link the 16" (plus Taobao/A&W/Twinsco earlier)
# odd old prices: link supplier, leave price empty until checked
SKIP_PRICE = {"ING-538", "ING-561", "ING-571"}
# conflicting old prices across suppliers: link every supplier that exists here, no price, default only if old item had one
CONFLICT = {"ING-593", "ING-614", "ING-544"}
PRICE_LIST = "Standard Buying"


def _pick(old):
	sup = next((d["default_supplier"] for d in old["defaults"] if d["default_supplier"]), None) \
		or next((s["supplier"] for s in old["suppliers"] if s["supplier"]), None)
	if not sup:
		named = [p for p in old["prices"] if p["supplier"]]
		sup = named[0]["supplier"] if named else None
	return sup, next((p for p in old["prices"] if p["supplier"] == sup), None)


def run(dry_run=True):
	company = frappe.defaults.get_global_default("company")
	src = json.load(open("/tmp/old_new_items_source.json"))
	mapping = json.load(open("/tmp/new_item_codes.json"))
	c = {"suppliers_created": 0, "links_added": 0, "prices_added": 0, "no_supplier": 0, "unmatched_supplier": 0, "no_old_price": 0}
	unmatched = {}
	try:
		for name, grp in CREATE.items():
			if not frappe.db.exists("Supplier", name):
				frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": grp,
					"supplier_type": "Company", "country": COUNTRY.get(name)}).insert(ignore_permissions=True)
				c["suppliers_created"] += 1; print("NEW SUPPLIER", name)
		for old_code, new_code in sorted(mapping.items()):
			item = frappe.get_doc("Item", new_code)
			primary = re.search(r"Old code: (ING-\d+)", item.description or "").group(1)
			old = src[old_code]
			sup, price = _pick(old)
			extra = old_code != primary
			if new_code in CONFLICT:
				names = list(dict.fromkeys([d["default_supplier"] for d in old["defaults"] if d["default_supplier"]] + [p["supplier"] for p in old["prices"] if p["supplier"]]))
				def_old = next((d["default_supplier"] for d in old["defaults"] if d["default_supplier"]), None)
				for n in names:
					sid = ALIAS.get(n)
					if not sid or not frappe.db.exists("Supplier", sid):
						print("CONFLICT", new_code, item.item_name, "supplier not on hcl-erp, not linked:", n); continue
					if not any(s.supplier == sid for s in item.supplier_items):
						item.append("supplier_items", {"supplier": sid}); c["links_added"] += 1
						print("CONFLICT", new_code, item.item_name, "linked:", sid)
					if n == def_old and company and not any(d.company == company for d in item.item_defaults):
						item.append("item_defaults", {"company": company, "default_supplier": sid})
				item.save(ignore_permissions=True)
				continue
			if not sup:
				c["no_supplier"] += 1; continue
			if sup not in ACTIVE:
				continue
			sid = ALIAS.get(sup)
			if not sid or not frappe.db.exists("Supplier", sid):
				c["unmatched_supplier"] += 1; unmatched.setdefault(sup, []).append(f"{new_code} {item.item_name}"); continue
			changed = False
			if not any(s.supplier == sid for s in item.supplier_items):
				item.append("supplier_items", {"supplier": sid}); changed = True
			if company and not extra and not any(d.company == company for d in item.item_defaults):
				item.append("item_defaults", {"company": company, "default_supplier": sid}); changed = True
			if changed:
				item.save(ignore_permissions=True); c["links_added"] += 1
			if extra and old_code in EXTRA:
				rate = EXTRA[old_code]["rate"]
			elif extra:
				rate = None  # same supplier as the kept item (cacao/eggs-g): kept item's own price stands
			else:
				rate = price["price_list_rate"] if price else None
			if new_code in SKIP_PRICE:
				print("SKIPPED ODD PRICE", new_code, item.item_name, rate); continue
			if not rate:
				if not extra: c["no_old_price"] += 1
				continue
			if not frappe.db.exists("Item Price", {"item_code": new_code, "supplier": sid, "price_list": PRICE_LIST}):
				frappe.get_doc({"doctype": "Item Price", "item_code": new_code, "price_list": PRICE_LIST, "supplier": sid,
					"buying": 1, "uom": item.stock_uom, "currency": (price or {}).get("currency") or "HKD",
					"price_list_rate": round(float(rate), 6),
					"note": EXTRA.get(old_code, {}).get("note", f"From old system {old_code}")}).insert(ignore_permissions=True)
				c["prices_added"] += 1; print("PRICE", new_code, rate, item.stock_uom)
		print("COUNTS", json.dumps(c))
		for s, its in unmatched.items():
			print("UNMATCHED", s, "->", "; ".join(its))
		print("TOTALS", frappe.db.sql("""select count(distinct i.name), count(distinct s.parent), count(distinct p.item_code)
			from tabItem i left join `tabItem Supplier` s on s.parent=i.name left join `tabItem Price` p on p.item_code=i.name and p.buying=1
			where i.name between 'ING-531' and 'ING-639'""")[0], "(items, with supplier, with price)")
	finally:
		if dry_run:
			frappe.db.rollback(); print("DRY RUN - rolled back")
	if not dry_run:
		frappe.db.commit(); print("COMMITTED")
