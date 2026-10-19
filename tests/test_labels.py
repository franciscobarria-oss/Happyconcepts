import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.hk_operations import label_data as ld  # noqa: E402

# A cookie (batch of 10) made from a dough batch preparation, plus eggs counted in pieces.
RECIPE_FOR_ITEM = {
	"COOKIE": {"recipe": "R-COOKIE", "batch_yield": 10},
	"DOUGH": {"recipe": "R-DOUGH", "batch_yield": 1000},  # 1000 g of dough per batch
}
LINES = {
	"R-COOKIE": [
		{"item": "DOUGH", "gross_qty": 400, "stock_uom": "Gram", "component_type": "Batch Preparation"},
		{"item": "CHOC", "gross_qty": 100, "stock_uom": "Gram"},
		{"item": "BAG", "gross_qty": 10, "stock_uom": "Nos", "component_type": "Packaging"},
	],
	"R-DOUGH": [
		{"item": "FLOUR-A", "gross_qty": 300, "stock_uom": "Gram"},
		{"item": "FLOUR-B", "gross_qty": 200, "stock_uom": "Gram"},
		{"item": "BUTTER", "gross_qty": 0.4, "stock_uom": "Kg"},
		{"item": "EGG", "gross_qty": 2, "stock_uom": "Nos"},
	],
}


def test_sub_recipes_are_broken_down_and_packaging_left_out():
	w, warn = ld.ingredient_weights("COOKIE", RECIPE_FOR_ITEM, LINES, {"EGG": 50}, qty=1)
	# one cookie = 40 g dough + 10 g chocolate; dough is 30% A, 20% B, 40% butter, 100 g eggs per 1000 g
	assert w["CHOC"] == pytest.approx(10)
	assert w["FLOUR-A"] == pytest.approx(12)
	assert w["FLOUR-B"] == pytest.approx(8)
	assert w["BUTTER"] == pytest.approx(16)
	assert w["EGG"] == pytest.approx(4)
	assert "BAG" not in w and "DOUGH" not in w
	assert warn == []


def test_pieces_without_weight_are_flagged():
	w, warn = ld.ingredient_weights("COOKIE", RECIPE_FOR_ITEM, LINES, {}, qty=1)
	assert w["EGG"] == 0
	assert warn == ["no-weight:EGG"]


def test_sales_unit_factor_scales_everything():
	one, _ = ld.ingredient_weights("COOKIE", RECIPE_FOR_ITEM, LINES, {"EGG": 50}, qty=1)
	box, _ = ld.ingredient_weights("COOKIE", RECIPE_FOR_ITEM, LINES, {"EGG": 50}, qty=200)
	assert box["CHOC"] == pytest.approx(one["CHOC"] * 200)


def test_a_recipe_using_itself_does_not_loop():
	rfi = {"X": {"recipe": "RX", "batch_yield": 1}}
	lines = {"RX": [{"item": "X", "gross_qty": 5, "stock_uom": "Gram"}, {"item": "S", "gross_qty": 1, "stock_uom": "Gram"}]}
	w, _ = ld.ingredient_weights("X", rfi, lines, {})
	assert w == {"X": 5, "S": 1}


def test_same_label_name_is_merged_and_sorted_heaviest_first():
	w = {"FLOUR-A": 12, "FLOUR-B": 8, "BUTTER": 16, "CHOC": 10, "EGG": 0}
	names = {"FLOUR-A": "Wheat flour", "FLOUR-B": "wheat flour ", "BUTTER": "Butter", "CHOC": "Dark chocolate", "EGG": "Egg"}
	rows = ld.ingredient_list(w, names)
	assert [r["name"] for r in rows] == ["Wheat flour", "Butter", "Dark chocolate", "Egg"]
	assert rows[0]["grams"] == 20 and sorted(rows[0]["items"]) == ["FLOUR-A", "FLOUR-B"]
	assert ld.ingredients_text(rows) == "Wheat flour, Butter, Dark chocolate, Egg"


def test_allergens_in_standard_order_without_duplicates():
	got = ld.allergens_for(["A", "B", "C"], {"A": ["Milk", "Gluten"], "B": ["Gluten"], "C": []}, ["Gluten", "Eggs", "Milk"])
	assert got == ["Gluten", "Milk"]


def test_label_quantities():
	assert ld.label_quantities(200, 48) == [48, 48, 48, 48, 8]
	assert ld.label_quantities(3, 1) == [1, 1, 1]
	assert ld.label_quantities(96, 48) == [48, 48]
	assert ld.label_quantities(2.5, 1) == [1, 1, 1]  # part pieces still need a label
	assert ld.label_quantities(0, 1) == []
	assert ld.label_quantities(5, 0) == [1] * 5


def test_dates_and_lot():
	d = ld.label_dates(date(2026, 10, 14), 5)
	assert d["best_before"] == date(2026, 10, 19)
	assert d["lot"] == "L261014"
	assert ld.fmt_date(d["best_before"]) == "19/10/2026"
	assert ld.label_dates(date(2026, 12, 30), 3)["best_before"] == date(2027, 1, 2)
	assert ld.label_dates(date(2026, 10, 14), 0)["best_before"] is None


def test_signature_ignores_dates_but_not_ingredients():
	a = {"title": "Cookie", "ingredients": "Flour, Butter", "allergens": ["Gluten", "Milk"], "shelf_life_days": 5}
	b = dict(a, made_on="2026-10-14")
	c = dict(a, ingredients="Flour, Margarine")
	d = dict(a, allergens=["Gluten"])
	assert ld.content_signature(a) == ld.content_signature(b)
	assert ld.content_signature(a) != ld.content_signature(c)
	assert ld.content_signature(a) != ld.content_signature(d)


def test_missing_for_approval():
	ok = {"ingredients": "Flour", "shelf_life_days": 5, "storage": "Keep refrigerated.", "unchecked_allergens": [], "no_weight": []}
	assert ld.missing_for_approval(ok) == []
	bad = dict(ok, shelf_life_days=0, storage="", unchecked_allergens=["ING-1"], no_weight=["ING-2"])
	msgs = ld.missing_for_approval(bad)
	assert len(msgs) == 4 and any("ING-1" in m for m in msgs) and any("ING-2" in m for m in msgs)


def test_suggest_allergens():
	kw = {"Gluten": ["flour", "wheat"], "Milk": ["butter", "milk"], "Tree nuts": ["hazelnut", "nutella"]}
	assert ld.suggest_allergens("Blue Ribbon Cake Flour", kw) == ["Gluten"]
	assert ld.suggest_allergens("Butter(Unsalted Butter)", kw) == ["Milk"]
	assert ld.suggest_allergens("Nutella", kw) == ["Tree nuts"]
	assert ld.suggest_allergens("Table Salt", kw) == []


def test_contains_sentence_uses_label_wording():
	assert ld.contains_sentence(["cereals containing gluten", "eggs", "tree nuts"]) == (
		"This product contains cereals containing gluten, eggs, tree nuts and their products.")
	assert ld.contains_sentence([]) == ""


def test_net_text():
	assert ld.net_text(80, 1, 1) == "Net Weight : 80g"
	assert ld.net_text(45, 48, 8) == "Contents : 8 x 45g"
	assert ld.net_text(0, 48, 48) == "Contents : 48 pcs"
	assert ld.net_text(0, 1, 1) == ""


def test_barcode_problem_blocks_the_check():
	ok = {"ingredients": "Flour", "shelf_life_days": 5, "storage": "x"}
	assert ld.missing_for_approval(dict(ok, barcode_error="bad digit")) == ["The barcode can't be printed: bad digit"]


# ---- drawing and ZPL (needs Pillow, the fonts and python-barcode, as in the ERP image) ----

lr = pytest.importorskip("happy_kitchen.hk_operations.label_render")

# the label scanned on 2026-10-14
SAMPLE = {
	"title": "Grab & Go \u2013 Black Sesame Cookie",
	"ingredients": "Margarine, Cake Flour, Bread Flour, Brown Sugar, White Sugar, Black Sesame Powder, Eggs, "
	               "Black Sesame Paste, Baking Soda, Baking Powder, Bamboo Charcoal Powder, Salt",
	"contains": "This product contains cereals containing gluten, eggs, tree nuts and their products.",
	"net": "Net Weight : 80g",
	"storage": "Storage : Store in a cool dry place",
	"maker": ["Happy Concepts Food Ltd.", "Flat D, 7/F, Derrick Industrial Building,", "49-51 Wong Chuk Hang Road, Hong Kong"],
	"origin": "Made in Hong Kong",
	"note": "For immediate consumption after opening",
	"factory": "Produced in a factory where tree nuts, fish, eggs, milk, peanuts, soybeans, crustaceans, "
	           "cereals containing gluten and their products are also handled",
	"best_before": "07/10/2026",
	"barcode": {"type": "CODE-39", "value": "798816138"},
}


def test_render_is_landscape_and_turns_for_portrait_rolls():
	img = lr.render(SAMPLE, 100, 150, 203)
	assert img.size == (1199, 799) and img.mode == "1"
	assert lr.render(SAMPLE, 150, 100, 300).size == (1772, 1181)
	assert lr.for_printer(img, 100, 150).size == (799, 1199)
	assert lr.for_printer(img, 150, 100).size == (1199, 799)
	black = img.convert("L").histogram()[0]
	assert 0.03 < black / (img.size[0] * img.size[1]) < 0.5


def test_long_ingredient_lists_still_fit():
	long = dict(SAMPLE, ingredients=", ".join(f"Ingredient number {n}" for n in range(60)))
	assert lr.render(long, 100, 150, 203).size == (1199, 799)


def test_barcodes():
	bars, text = lr.barcode_modules("CODE-39", "798816138")
	assert text == "*798816138*" and set(bars) == {"0", "1"}
	bars, text = lr.barcode_modules("EAN", "4891234567898")
	assert len(bars) == 95 and text == "4891234567898"
	assert lr.barcode_modules("", "1000025664")[1] == "1000025664"  # Code 128
	with pytest.raises(Exception):
		lr.barcode_modules("CODE-39", "abc~")
	# an invalid barcode doesn't stop the rest of the label
	with_bad = lr.render(dict(SAMPLE, barcode={"type": "CODE-39", "value": "abc~"}))
	without = lr.render(dict(SAMPLE, barcode=None))
	assert with_bad.tobytes() == without.tobytes()


def test_zpl_count_letters():
	assert lr._count(1) == "G"
	assert lr._count(19) == "Y"
	assert lr._count(20) == "g"
	assert lr._count(41) == "hG"
	assert lr._count(400) == "z"
	assert lr._count(819) == "zzY"


def test_zpl_round_trip_matches_the_picture():
	img = lr.for_printer(lr.render(SAMPLE, 100, 150, 203), 100, 150)
	zpl = lr.to_zpl(img, copies=3)
	assert zpl.startswith("^XA^PW799^LL1199") and "^PQ3^XZ" in zpl
	w, h = img.size
	bpr = (w + 7) // 8
	rows = lr.zpl_graphic_to_rows(zpl)
	assert len(rows) == h
	px = img.load()
	for y in range(0, h, 7):  # every 7th row, every dot
		bits = bin(int(rows[y], 16))[2:].zfill(bpr * 8)
		for x in range(w):
			assert (bits[x] == "1") == (px[x, y] == 0), (x, y)
		assert bits[w:] == "0" * (bpr * 8 - w)  # padding is white
	assert len(zpl) < bpr * h * 2 / 3


def test_label_check_rows():
	items = [
		{"name": "FLOUR", "item_name": "Flour T55 25kg", "hk_label_name": "Wheat flour", "hk_allergens_checked": 1},
		{"name": "BUTTER", "item_name": "Butter", "hk_label_name": "", "hk_allergens_checked": 0},
		{"name": "DOUGH", "item_name": "Dough", "hk_label_name": "", "hk_allergens_checked": 0},
		{"name": "SPARE", "item_name": "Unused", "hk_label_name": "", "hk_allergens_checked": 0},
	]
	used = {"FLOUR": {"R1", "R2"}, "BUTTER": {"R1"}, "DOUGH": {"R2"}}
	rows = ld.label_check_rows(items, {"FLOUR": ["Gluten"], "BUTTER": ["Milk"]}, used, {"DOUGH"})
	assert [r["item"] for r in rows] == ["BUTTER", "FLOUR"]  # sub-recipe and unused items left out
	butter, flour = rows
	assert butter["prints_as"] == "Butter" and butter["to_do"] == "label name, allergen review"
	assert flour == {"item": "FLOUR", "item_name": "Flour T55 25kg", "label_name": "Wheat flour", "prints_as": "Wheat flour",
	                 "allergens": "Gluten", "allergens_reviewed": 1, "recipes": 2, "to_do": ""}
	assert [r["item"] for r in ld.label_check_rows(items, {}, used, {"DOUGH"}, only_open=True)] == ["BUTTER"]
