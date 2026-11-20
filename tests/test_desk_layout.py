"""The desk is ten workspaces in the requested order, every one has its files, nothing else shows."""

import json
from pathlib import Path

from happy_kitchen.setup import desk_layout as d

APP = Path(__file__).resolve().parent.parent / "happy_kitchen"


def test_ten_in_order_plus_stock_take_outside():
	assert len(d.TEN) == 10 and d.OUTSIDE == ["Stock Take"]
	order = [json.loads((APP / "desktop_icon" / f"{n.lower().replace(' ', '_')}.json").read_text())["idx"] for n in d.OURS]
	assert order == sorted(order) and len(set(order)) == len(order)


def test_every_workspace_has_workspace_sidebar_and_icon():
	for n in d.OURS:
		stem = n.lower().replace(" ", "_")
		assert (APP / "workspace_sidebar" / f"{stem}.json").exists(), n
		assert (APP / "desktop_icon" / f"{stem}.json").exists(), n
		ws = list(APP.glob(f"*/workspace/*/{stem}.json"))
		assert len(ws) == 1, n
		assert json.loads(ws[0].read_text())["name"] == n


def test_workspace_shortcut_names_are_unique_and_used():
	for f in APP.glob("*/workspace/*/*.json"):
		doc = json.loads(f.read_text())
		labels = [s["label"] for s in doc["shortcuts"]]
		assert len(labels) == len(set(labels)), doc["name"]
		used = [b["data"]["shortcut_name"] for b in json.loads(doc["content"]) if b["type"] == "shortcut"]
		assert sorted(used) == sorted(labels), doc["name"]


def test_hides_the_rest_but_keeps_ours_parent_and_admin():
	icons = [{"name": "Recipes", "parent_icon": "ERPNext"}, {"name": "ERPNext", "parent_icon": ""},
	         {"name": "Stock", "parent_icon": "ERPNext"}, {"name": "Buying", "parent_icon": "ERPNext", "hidden": 1},
	         {"name": "Settings", "parent_icon": ""}, {"name": "Payroll", "parent_icon": "Frappe HR"}]
	assert d.to_hide(icons) == ["Stock", "Payroll"]
