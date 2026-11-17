from happy_kitchen.hk_operations.auto_confirm import DUPLICATE, NO_PRICE, ZERO_VALUE, hold_reason


def test_normal_order_goes_through():
	assert hold_reason(1019.2, [10, 20.5], False) == ""


def test_zero_value_is_held():
	assert hold_reason(0, [0, 0], False) == ZERO_VALUE
	assert hold_reason(None, [], False) == ZERO_VALUE


def test_a_line_without_price_is_held():
	assert hold_reason(50, [50, 0], False) == NO_PRICE


def test_duplicate_is_held():
	assert hold_reason(50, [50], True) == DUPLICATE
