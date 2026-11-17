import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from happy_kitchen.hk_operations import list_price as lp  # noqa: E402

A = {"supplier": "Hop Lee", "rate": 418.0, "uom": "Tub", "currency": "HKD", "valid_from": "2026-10-01"}
B = {"supplier": "PARKnSHOP", "rate": 39, "uom": "Jar", "currency": "HKD", "valid_from": "2026-11-01"}


def test_text():
	assert lp.price_text(A) == "HKD 418 / Tub"
	assert lp.price_text({"rate": 0.0125, "currency": "HKD", "uom": "Gram"}) == "HKD 0.0125 / Gram"
	assert lp.price_text(None) == ""


def test_pick():
	assert lp.pick([A, B]) is B  # newest
	assert lp.pick([A, B], ["Hop Lee"]) is A  # first listed supplier wins
	assert lp.pick([B], ["Hop Lee"]) is B
	assert lp.pick([]) is None
