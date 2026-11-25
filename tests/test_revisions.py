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


def test_po_action():
	from happy_kitchen.hk_operations import revisions as r
	d = [("A", 5, 8)]
	assert r.po_action([], 1)[0] == r.UNCHANGED
	assert r.po_action(d, 0)[0] == r.APPLY
	assert r.po_action(d, 1, "To Deliver and Bill")[0] == r.APPLY
	assert r.po_action(d, 1, "To Bill", per_delivered=100)[0] == r.MANUAL
	assert r.po_action(d, 1, "To Deliver", per_billing=10)[0] == r.MANUAL
	assert r.po_action(d, 1, "Closed")[0] == r.MANUAL
	assert r.po_action(d, 2)[0] == r.MANUAL


def test_keep_unmentioned_never_drops_rows():
	old = [{"item_code": "RV", "qty": 4}, {"item_code": "PB", "qty": 2}, {"item_code": "AP", "qty": 6}]
	new = [{"item_code": "RV", "qty": 10}]
	full = r.keep_unmentioned(old, new)
	assert r.normalize(full) == {"RV": 10.0, "PB": 2.0, "AP": 6.0}
	assert r.changes(old, full) == [("RV", 4.0, 10.0)]
	assert r.changes(old, r.keep_unmentioned(old, [])) == []
