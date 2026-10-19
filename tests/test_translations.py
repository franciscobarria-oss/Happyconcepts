"""Every user-facing string is translated, or deliberately left to ERPNext, and the CSV
Frappe reads matches zh_tw_source.py."""

import csv
from pathlib import Path

from happy_kitchen.translations import strings
from happy_kitchen.translations.zh_tw_source import LEAVE_AS_IS, ZH_TW

CSV = Path(strings.APP_DIR) / "translations" / "zh-TW.csv"

# Words ERPNext already translates; overriding them would change them all over ERPNext.
GENERIC = {"Rate", "Batch", "Pending", "Rejected", "Status", "Company", "Draft", "Supplier", "Item", "Qty", "Date",
           "Warehouse", "Active", "Approved", "Submitted"}


def test_every_string_has_a_translation():
	missing = sorted(s for s in strings.collect() if s not in ZH_TW and s not in LEAVE_AS_IS)
	assert not missing, "add to zh_tw_source.ZH_TW (or LEAVE_AS_IS): " + "; ".join(missing[:20])


def test_generic_erpnext_words_are_not_overridden():
	assert not GENERIC & set(ZH_TW)
	assert not LEAVE_AS_IS & set(ZH_TW)


def test_translations_are_chinese_and_keep_placeholders():
	for en, zh in ZH_TW.items():
		assert zh.strip(), en
		for i in range(6):
			ph = "{%d}" % i
			assert (ph in en) == (ph in zh), f"placeholder {ph} differs: {en!r}"


def test_csv_matches_source():
	with CSV.open(encoding="utf-8", newline="") as f:
		rows = {r[0]: r[1] for r in csv.reader(f)}
	assert rows == ZH_TW, "run: python3 happy_kitchen/translations/zh_tw_source.py"


def test_extractor_reads_js_py_and_json():
	assert strings.strings_from_js("x = __('Save PIN'); y = __(\"A \\\"b\\\"\"); z = __(`Tpl`)") == {"Save PIN", 'A "b"', "Tpl"}
	assert strings.strings_from_py('frappe.throw(_("Row {0}: bad").format(1))') == {"Row {0}: bad"}
	doc = {"doctype": "DocType", "name": "Wastage Log", "fields": [
		{"label": "Reason", "fieldtype": "Select", "options": "\nSpoiled\nkg"},
		{"label": "Series", "fieldtype": "Select", "options": "WST-.YYYY.-.####"}]}
	assert strings.strings_from_json(doc) == {"Wastage Log", "Reason", "Spoiled", "kg", "Series"}
	page = {"doctype": "Page", "name": "stock-take-count", "title": "Stock Take Count"}
	assert strings.strings_from_json(page) == {"Stock Take Count"}
