from happy_kitchen.hk_operations import revisions as r


def L(**kw):
	return [{"item_code": k, "qty": v} for k, v in kw.items()]


def test_normalize_merges_lines_and_drops_empty():
	rows = [{"item_code": "A", "qty": 2}, {"item_code": "A", "qty": 3}, {"item_code": "B", "qty": 0}, {"item_code": None, "qty": 4}]
	assert r.normalize(rows) == {"A": 5.0}


def test_no_change_is_not_a_revision():
	assert r.changes(L(A=2, B=1), [{"item_code": "B", "qty": 1}, {"item_code": "A", "qty": 2}]) == []


def test_added_removed_and_changed():
	diff = r.changes(L(A=12, B=6), L(A=18, C=24))
	assert diff == [("A", 12, 18), ("B", 6, 0), ("C", 0, 24)]
	assert r.summary(diff, {"A": "Brownie", "B": "Scone"}) == "Brownie: 12 → 18; Scone: removed (was 6); C: added 24"
