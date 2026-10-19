import pytest

from happy_kitchen.recipe_management import variance as v

# Recipes per batch, quantities in stock UOM (Gram / Nos)
LINES = {
	# cookie: 1000 cookies per batch, uses 2 kg of a fresh "choc ganache" component and frozen dough
	"COOKIE": [
		{"item": "FLOUR", "gross_qty": 40000},
		{"item": "EGG", "gross_qty": 600},
		{"item": "GANACHE", "gross_qty": 2000},
		{"item": "DOUGH", "gross_qty": 5000},
	],
	# component: 1 batch = 1000 g of ganache
	"GANACHE-R": [
		{"item": "CHOC", "gross_qty": 600},
		{"item": "CREAM", "gross_qty": 400},
	],
	# batch preparation: 1 batch = 10,000 g of dough
	"DOUGH-R": [
		{"item": "FLOUR", "gross_qty": 6000},
		{"item": "BUTTER", "gross_qty": 4000},
	],
	"WRAP": [{"item": "TORTILLA", "gross_qty": 1}, {"item": "CHICKEN", "base_qty": 120}],
}
SUBS = {
	"GANACHE": {"recipe": "GANACHE-R", "recipe_type": "Recipe Component", "batch_yield": 1000},
	"DOUGH": {"recipe": "DOUGH-R", "recipe_type": "Batch Preparation", "batch_yield": 10000},
}


def test_expand_usage_scales_by_batches():
	u = v.expand_usage([{"recipe": "COOKIE", "batches": 2}], LINES, SUBS)
	assert u["FLOUR"] == 80000
	assert u["EGG"] == 1200


def test_recipe_component_is_broken_down_into_its_ingredients():
	u = v.expand_usage([{"recipe": "COOKIE", "batches": 1}], LINES, SUBS)
	assert "GANACHE" not in u
	# 2000 g of ganache = 2 batches of a 1000 g recipe
	assert u["CHOC"] == pytest.approx(1200)
	assert u["CREAM"] == pytest.approx(800)


def test_batch_preparation_stays_as_its_own_item():
	u = v.expand_usage([{"recipe": "COOKIE", "batches": 1}], LINES, SUBS)
	assert u["DOUGH"] == 5000
	assert "BUTTER" not in u  # counted when the dough itself is produced


def test_producing_the_batch_preparation_counts_its_ingredients_once():
	runs = [{"recipe": "DOUGH-R", "batches": 1}, {"recipe": "COOKIE", "batches": 1}]
	u = v.expand_usage(runs, LINES, SUBS)
	assert u["FLOUR"] == 6000 + 40000
	assert u["BUTTER"] == 4000


def test_nested_components_expand_recursively():
	lines = {"A": [{"item": "B", "gross_qty": 50}], "B-R": [{"item": "C", "gross_qty": 10}], "C-R": [{"item": "SALT", "gross_qty": 2}]}
	subs = {"B": {"recipe": "B-R", "recipe_type": "Recipe Component", "batch_yield": 10},
	        "C": {"recipe": "C-R", "recipe_type": "Recipe Component", "batch_yield": 1}}
	# 50 B = 5 batches of B-R -> 50 C = 50 batches of C-R -> 100 SALT
	assert v.expand_usage([{"recipe": "A", "batches": 1}], lines, subs) == {"SALT": pytest.approx(100)}


def test_recipe_loop_is_reported():
	lines = {"X-R": [{"item": "Y", "gross_qty": 1}], "Y-R": [{"item": "X", "gross_qty": 1}]}
	subs = {"X": {"recipe": "X-R", "recipe_type": "Recipe Component", "batch_yield": 1},
	        "Y": {"recipe": "Y-R", "recipe_type": "Recipe Component", "batch_yield": 1}}
	with pytest.raises(v.VarianceError):
		v.expand_usage([{"recipe": "X-R", "batches": 1}], lines, subs)


def test_base_qty_used_when_gross_missing():
	assert v.expand_usage([{"recipe": "WRAP", "batches": 3}], LINES, SUBS) == {"TORTILLA": 3, "CHICKEN": 360}


def test_sales_runs_skip_items_produced_in_the_period():
	recipe_for_item = {"COOKIE-SKU": {"recipe": "COOKIE", "batch_yield": 1000}, "WRAP-SKU": {"recipe": "WRAP", "batch_yield": 1}}
	sales = {"COOKIE-SKU": 3000, "WRAP-SKU": 40, "COKE": 10}
	runs = v.runs_from_sales(sales, recipe_for_item, produced_items={"COOKIE-SKU"})
	assert runs == [{"recipe": "WRAP", "batches": 40.0}]  # cookies come from production, coke has no recipe


def test_batch_preparation_sold_as_is_is_not_expanded():
	recipe_for_item = {"DOUGH": {"recipe": "DOUGH-R", "recipe_type": "Batch Preparation", "batch_yield": 10000}}
	assert v.runs_from_sales({"DOUGH": 5000}, recipe_for_item, set()) == []
	assert v.sold_as_is({"DOUGH": 5000, "COKE": 12}, recipe_for_item) == {"DOUGH": 5000, "COKE": 12}


def test_finished_products_are_not_sold_as_is():
	assert v.sold_as_is({"COOKIE-SKU": 1000}, {"COOKIE-SKU": {"recipe": "COOKIE", "recipe_type": "Finished Product"}}) == {}


def test_sales_runs_convert_units_to_batches():
	runs = v.runs_from_sales({"COOKIE-SKU": 2500}, {"COOKIE-SKU": {"recipe": "COOKIE", "batch_yield": 1000}}, set())
	assert runs == [{"recipe": "COOKIE", "batches": 2.5}]


@pytest.mark.parametrize("qty,uom,stock_uom,expected", [
	(2.5, "kg", "Gram", 2500), (750, "g", "Gram", 750), (1.5, "l", "Gram", 1500), (12, "piece", "Nos", 12),
])
def test_count_unit_conversion(qty, uom, stock_uom, expected):
	assert v.count_to_stock_qty(qty, uom, stock_uom) == pytest.approx(expected)


def test_count_in_pieces_for_gram_item_needs_piece_weight():
	with pytest.raises(v.VarianceError):
		v.count_to_stock_qty(3, "piece", "Gram")
	assert v.count_to_stock_qty(3, "piece", "Gram", grams_per_piece=250) == 750


def test_default_count_uom():
	assert v.default_count_uom("Gram") == "g"
	assert v.default_count_uom("Nos") == "piece"


def test_actual_usage_formula():
	assert v.actual_usage(opening=1000, received=5000, closing=1500) == 4500
	assert v.actual_usage(opening=0, received=0, closing=2000, produced=10000) == 8000


def test_variance_inside_and_outside_tolerance():
	inside = v.variance_row(actual=1015, expected=1000, unit_cost=0.01, tolerance_pct=2)
	assert inside["variance_qty"] == 15 and inside["variance_pct"] == pytest.approx(1.5) and inside["within_tolerance"]
	outside = v.variance_row(actual=1100, expected=1000, unit_cost=0.01, tolerance_pct=2)
	assert outside["variance_pct"] == pytest.approx(10) and not outside["within_tolerance"]
	assert outside["variance_cost"] == pytest.approx(1.0)
	under = v.variance_row(actual=970, expected=1000, unit_cost=1, tolerance_pct=2)
	assert under["variance_pct"] == pytest.approx(-3) and not under["within_tolerance"]
	edge = v.variance_row(actual=1020, expected=1000, unit_cost=1, tolerance_pct=2)
	assert edge["within_tolerance"]


def test_tolerance_is_a_parameter():
	assert v.variance_row(1050, 1000, 1, tolerance_pct=5)["within_tolerance"]
	assert not v.variance_row(1050, 1000, 1, tolerance_pct=2)["within_tolerance"]


def test_usage_with_nothing_expected():
	r = v.variance_row(actual=50, expected=0, unit_cost=1)
	assert r["variance_pct"] is None and not r["within_tolerance"]
	assert v.variance_row(0, 0, 1)["within_tolerance"]


def test_totals_are_cost_weighted():
	rows = [v.variance_row(1015, 1000, 0.01), v.variance_row(110, 100, 1.0)]
	t = v.totals(rows)
	assert t["variance_cost"] == pytest.approx(0.15 + 10)
	assert t["variance_pct"] == pytest.approx(10.15 / 110 * 100)
	assert t["out_of_tolerance"] == 1


# approval rules
APPROVER = ["Stock User", "Stock Take Approver"]


def test_draft_can_be_submitted_by_anyone():
	assert v.check_transition("submit", "Draft", "kitty@hk", None, ["Stock User"]) == "Submitted"


def test_cannot_submit_twice_or_after_approval():
	for status in ("Submitted", "Approved"):
		with pytest.raises(v.VarianceError):
			v.check_transition("submit", status, "kitty@hk", None, APPROVER)


def test_approval_needs_the_approver_role():
	with pytest.raises(v.VarianceError):
		v.check_transition("approve", "Submitted", "brian@hk", "kitty@hk", ["Stock Manager", "System Manager"])
	assert v.check_transition("approve", "Submitted", "brian@hk", "kitty@hk", APPROVER) == "Approved"


def test_submitter_cannot_approve_or_reject_own_count():
	for action in ("approve", "reject"):
		with pytest.raises(v.VarianceError):
			v.check_transition(action, "Submitted", "kitty@hk", "kitty@hk", APPROVER, comment="x")


def test_only_submitted_counts_can_be_approved():
	for status in ("Draft", "Approved"):
		with pytest.raises(v.VarianceError):
			v.check_transition("approve", status, "brian@hk", "kitty@hk", APPROVER)


def test_rejection_needs_a_comment_and_returns_to_draft():
	with pytest.raises(v.VarianceError):
		v.check_transition("reject", "Submitted", "brian@hk", "kitty@hk", APPROVER, comment="  ")
	assert v.check_transition("reject", "Submitted", "brian@hk", "kitty@hk", APPROVER, comment="flour looks off") == "Draft"


def test_rejected_count_can_be_resubmitted():
	assert v.check_transition("submit", "Rejected", "kitty@hk", "kitty@hk", ["Stock User"]) == "Submitted"


def test_alias_skus_fold_onto_the_recipe_item():
	aliases = {"798815002": ("IK0008", 1), "CKBOAT30": ("RJ0049", 100)}
	sales = {"798815002": 30, "IK0008": 10, "CKBOAT30": 2, "COKE": 5}
	assert v.fold_aliases(sales, aliases) == {"IK0008": 40, "RJ0049": 200, "COKE": 5}


def test_alias_of_a_produced_item_is_not_counted_twice():
	recipe_for_item = {"IK0008": {"recipe": "IK0008", "recipe_type": "Finished Product", "batch_yield": 1000}}
	sales = v.fold_aliases({"798815002": 3000}, {"798815002": ("IK0008", 1)})
	assert v.runs_from_sales(sales, recipe_for_item, produced_items={"IK0008"}) == []
	assert v.runs_from_sales(sales, recipe_for_item, produced_items=set()) == [{"recipe": "IK0008", "batches": 3.0}]


def test_dough_box_sold_as_is_counts_pieces():
	recipe_for_item = {"RJ0049": {"recipe": "RJ0049", "recipe_type": "Batch Preparation", "batch_yield": 1}}
	sales = v.fold_aliases({"CKBOAT30": 3}, {"CKBOAT30": ("RJ0049", 100)})
	assert v.sold_as_is(sales, recipe_for_item) == {"RJ0049": 300}


def test_pack_count_converts_packs_and_loose_units():
	# 2 boxes of 200 + 35 loose pieces
	assert v.pack_count_to_stock_qty(2, 200, 35, "piece", "Nos") == 435
	# 3 bags of 25 kg + 1.5 kg loose
	assert v.pack_count_to_stock_qty(3, 25000, 1.5, "kg", "Gram") == 76500
	assert v.pack_count_to_stock_qty(0, 0, 750, "g", "Gram") == 750


def test_pack_without_conversion_is_rejected():
	with pytest.raises(v.VarianceError):
		v.pack_count_to_stock_qty(2, 0, 0, "g", "Gram")


def test_three_pack_sizes_plus_loose():
	# 1 bag of 22.7 kg + 2 bags of 5 kg + 3 bags of 1 kg + 350 g loose
	packs = [(1, 22700), (2, 5000), (3, 1000)]
	assert v.packs_to_stock_qty(packs, 350, "g", "Gram") == 36050
	# empty boxes count as 0
	assert v.packs_to_stock_qty([(None, 22700), (0, 5000)], 0.5, "kg", "Gram") == 500
	assert v.packs_to_stock_qty([], 12, "piece", "Nos") == 12
	with pytest.raises(v.VarianceError):
		v.packs_to_stock_qty([(1, 22700), (1, 0)], 0, "g", "Gram")


def test_compact_packs_removes_gaps_and_repeats():
	assert v.compact_packs([None, "Bag", "Bag"]) == ["Bag"]
	assert v.compact_packs(["Case", "", "Box"]) == ["Case", "Box"]
	assert v.compact_packs([None, None, None]) == []


def test_suggest_packs_biggest_real_packs_first():
	conv = [("Gram", 1), ("Kg", 1000), ("Pack", 500), ("Case", 6000), ("Box", 3000), ("Tray", 250), ("Bag", 500)]
	assert v.suggest_packs(conv, "Gram") == ["Case", "Box", "Pack"]  # Bag repeats Pack's size; Tray is 4th
	assert v.suggest_packs([("Nos", 1), ("Dozen", 12)], "Nos") == ["Dozen"]
	assert v.suggest_packs([("Kg", 1000)], "Gram") == []


def test_wastage_explains_part_of_the_variance():
	r = v.variance_row(actual=1100, expected=1000, unit_cost=0.5, tolerance_pct=2, wastage=60)
	assert r["variance_qty"] == 100 and not r["within_tolerance"]
	assert r["wastage_qty"] == 60 and r["wastage_cost"] == pytest.approx(30)
	assert r["unexplained_qty"] == 40 and r["unexplained_cost"] == pytest.approx(20)


def test_totals_split_wastage_and_unexplained():
	t = v.totals([v.variance_row(1100, 1000, 0.5, wastage=60), v.variance_row(110, 100, 1.0)])
	assert t["wastage_cost"] == pytest.approx(30)
	assert t["unexplained_cost"] == pytest.approx(20 + 10)
	assert t["variance_cost"] == pytest.approx(60)


def test_pack_caption_in_words():
	assert v.pack_caption("Pack", 22700, "Gram") == "Pack 22.7 kg"
	assert v.pack_caption("Box", 454, "Gram") == "Box 454 g"
	assert v.pack_caption("Bag", 25000, "Gram") == "Bag 25 kg"
	assert v.pack_caption("Case", 360, "Nos") == "Case 360 pcs"
	assert v.pack_caption("Pack", 0, "Gram") == "Pack"


def test_fit_count_uom_replaces_weight_unit_on_count_item():
	# a Select field fills in its first option ('g'), even for eggs
	assert v.fit_count_uom("g", "Nos") == "piece"
	assert v.fit_count_uom(None, "Nos") == "piece"
	assert v.fit_count_uom("", "Gram") == "g"
	assert v.fit_count_uom("piece", "Gram") == "g"


def test_fit_count_uom_keeps_a_fitting_choice():
	assert v.fit_count_uom("kg", "Gram") == "kg"
	assert v.fit_count_uom("piece", "Nos") == "piece"
	# weight per piece makes either kind work
	assert v.fit_count_uom("g", "Nos", 60) == "g"
	# unknown stock unit: keep what was chosen
	assert v.fit_count_uom("l", "Bottle") == "l"
