"""Daily Sales Overview: one delivery day as a grid of products (rows) by
outlets (columns), the layout of the team's Daily_Sales_Overview_<ddmmyy>_A4
workbook. Pure maths, unit-tested in tests/test_daily_overview.py.

- Columns are customers that have an order for the day, grouped under a
  heading ("IKEA", "SODEXO"). A customer's heading and short name come from
  its sheet fields when set, otherwise from its name: "THE DAIRY FARM COMPANY
  LIMITED - CWB" -> heading "THE DAIRY FARM COMPANY LIMITED", column "CWB".
  GROUP_ALIASES turns known legal names into the short headings the team uses.
- Rows are items, in item code order. Each cell is the quantity ordered in the
  order's own unit; the same item on two orders for one outlet is added up.
- Best before = delivery day + the item's shelf life (blank when unknown).
- Footer per column: total quantity, invoice numbers, customer PO references,
  invoice total (sum of the outlet's order totals when there is no invoice
  yet) and the number of invoices.
"""

from __future__ import annotations

from datetime import date, timedelta

# Legal or Xero names -> the short heading on the sheet.
GROUP_ALIASES = {
	"THE DAIRY FARM COMPANY LIMITED": "IKEA",
	"PLAZA PREMIUM LOUNGE HKG": "PPL",
	"SODEXO": "SODEXO",
	"PK LIMITED": "PK",
	"NINETY SIX LIMITED (AFFEE)": "AFFEE",
	"SELECT SERVICE PARTNER HONG KONG LTD": "SSP",
}

# Short names the team writes differently from the Xero suffix.
LABEL_ALIASES = {
	"UNITED AIRLINES": "UA",
	"SINGAPORE AIRLINE": "SA",
	"SINGAPORE AIRLINES": "SA",
	"QANTAS AIRWAYS": "Qantas",
}

EPS = 1e-9


def _f(v) -> float:
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0


def column_for(customer: dict) -> dict:
	"""{"key", "group", "label", "label_zh", "sort"} for one customer.

	customer: name, customer_name and optionally hk_sheet_group, hk_sheet_label,
	hk_sheet_label_zh, hk_sheet_sort (fields set on the Customer)."""
	full = (customer.get("customer_name") or customer.get("name") or "").strip()
	parent, sep, outlet = full.partition(" - ")
	if not sep:
		parent, outlet = full, full
	parent, outlet = parent.strip(), outlet.strip()
	group = customer.get("hk_sheet_group") or GROUP_ALIASES.get(parent.upper()) or parent
	label = customer.get("hk_sheet_label") or LABEL_ALIASES.get(outlet.upper()) or outlet
	if not sep and not customer.get("hk_sheet_label"):
		label = group if customer.get("hk_sheet_group") else full
	return {
		"key": customer.get("name") or full,
		"group": group,
		"label": label,
		"label_zh": customer.get("hk_sheet_label_zh") or "",
		"sort": customer.get("hk_sheet_sort"),
	}


def best_before(day: date, shelf_life_days) -> date | None:
	days = int(_f(shelf_life_days))
	return day + timedelta(days=days) if days > 0 else None


def build_grid(day: date, lines: list[dict], customers: dict[str, dict], items: dict[str, dict],
               invoices: list[dict] | None = None) -> dict:
	"""lines: order lines for the day (sales_order, customer, item_code, item_name,
	qty, uom, po_no, so_grand_total). customers: {name: customer}. items: {code:
	{item_name, item_name_zh, shelf_life_days, sheet_code}}. invoices: {name,
	sales_order, grand_total} rows (one per invoice and order).

	Returns {"day", "columns", "rows", "totals", "grand_total", "footer"}."""
	invoices = invoices or []
	cols: dict[str, dict] = {}
	cells: dict[tuple, float] = {}
	orders_by_col: dict[str, dict[str, float]] = {}
	po_by_col: dict[str, list] = {}
	units: dict[tuple, set] = {}
	for l in lines:
		qty = _f(l.get("qty"))
		if qty <= EPS:
			continue
		cust = l["customer"]
		if cust not in cols:
			cols[cust] = column_for(customers.get(cust) or {"name": cust, "customer_name": l.get("customer_name") or cust})
		key = (l["item_code"], cust)
		cells[key] = cells.get(key, 0.0) + qty
		units.setdefault(l["item_code"], set()).add(l.get("uom") or "")
		orders_by_col.setdefault(cust, {})[l["sales_order"]] = _f(l.get("so_grand_total"))
		po = (l.get("po_no") or "").strip()
		if po and po not in po_by_col.setdefault(cust, []):
			po_by_col[cust].append(po)

	columns = sorted(cols.values(), key=lambda c: (
		c["sort"] if c["sort"] is not None else 10**6, c["group"].lower(), c["label"].lower()))

	inv_by_so: dict[str, dict[str, float]] = {}
	for inv in invoices:
		inv_by_so.setdefault(inv["sales_order"], {})[inv["name"]] = _f(inv.get("grand_total"))

	footer = []
	for c in columns:
		sos = orders_by_col.get(c["key"], {})
		invs: dict[str, float] = {}
		for so in sos:
			invs.update(inv_by_so.get(so, {}))
		invoiced = bool(invs)
		footer.append({
			"key": c["key"],
			"qty": sum(q for (i, k), q in cells.items() if k == c["key"]),
			"invoices": sorted(invs),
			"orders": sorted(sos),
			"po_refs": po_by_col.get(c["key"], []),
			"amount": sum(invs.values()) if invoiced else sum(sos.values()),
			"invoiced": invoiced,
			"invoice_count": len(invs),
		})

	rows = []
	for code in sorted({i for i, _ in cells}, key=lambda c: (str((items.get(c) or {}).get("sheet_code") or c))):
		info = items.get(code) or {}
		qtys = [cells.get((code, c["key"])) for c in columns]
		rows.append({
			"item_code": code,
			"sheet_code": info.get("sheet_code") or code,
			"item_name": info.get("item_name") or code,
			"item_name_zh": info.get("item_name_zh") or "",
			"best_before": best_before(day, info.get("shelf_life_days")),
			"uom": ", ".join(sorted(u for u in units.get(code, ()) if u)),
			"qtys": qtys,
			"total": sum(q for q in qtys if q),
		})
	return {
		"day": day,
		"columns": columns,
		"rows": rows,
		"footer": footer,
		"grand_total": sum(r["total"] for r in rows),
		"group_spans": group_spans(columns),
	}


def group_spans(columns: list[dict]) -> list[tuple[str, int]]:
	"""Consecutive columns under the same heading: [("IKEA", 11), ("PPL", 1), ...]."""
	spans: list[list] = []
	for c in columns:
		if spans and spans[-1][0] == c["group"]:
			spans[-1][1] += 1
		else:
			spans.append([c["group"], 1])
	return [(g, n) for g, n in spans]
