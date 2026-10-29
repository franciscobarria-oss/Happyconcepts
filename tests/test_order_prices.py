from happy_kitchen.hk_operations import order_prices as op


def test_missing_price_takes_the_po_price():
	r = op.check(12.5, 0)
	assert r["status"] == op.USED and r["fill"] and r["rate"] == 12.5
	assert op.check("12.5", None)["fill"]


def test_different_price_keeps_ours_and_is_flagged():
	r = op.check(10, 12)
	assert r["status"] == op.DIFFERS and not r["fill"] and r["rate"] == 12
	assert r["diff"] == -2 and r["pct"] == -16.7
	assert op.signed(r) == "−2.00, −16.7%"
	assert op.signed(op.check(13.5, 12)) == "+1.50, +12.5%"


def test_same_price_within_half_a_cent():
	assert op.check(12.004, 12)["status"] == op.SAME
	assert op.check(12.006, 12)["status"] == op.DIFFERS


def test_no_po_price():
	assert op.check(0, 12)["status"] == "" and op.check(None, 12)["rate"] == 12
	r = op.check(0, 0)
	assert r["status"] == op.NONE and not r["fill"] and r["rate"] == 0


def test_differs_and_money():
	assert op.differs(10, 12) and not op.differs(12, 12.001) and not op.differs(0, 12) and not op.differs(10, 0)
	assert op.money(12) == "12.00" and op.money(0.125) == "0.125" and op.money(1234.5) == "1,234.50"
	assert op.parse_price("HK$ 1,234.50") == 1234.5 and op.parse_price("n/a") == 0


def test_counts():
	assert op.counts([op.USED, op.DIFFERS, op.DIFFERS, "", op.NONE]) == {op.USED: 1, op.DIFFERS: 2, op.SAME: 0, op.NONE: 1}
