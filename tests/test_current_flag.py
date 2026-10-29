from happy_kitchen.hk_operations.current_flag import SUFFIX, apply_suffix, strip_suffix


def test_adds_suffix_once():
	assert apply_suffix("Tomato", 1) == "Tomato (current)"
	assert apply_suffix("Tomato (current)", 1) == "Tomato (current)"


def test_removes_suffix_when_unticked():
	assert apply_suffix("Tomato (current)", 0) == "Tomato"
	assert apply_suffix("Tomato", 0) == "Tomato"


def test_keeps_inside_140_chars():
	out = apply_suffix("x" * 200, 1)
	assert len(out) == 140 and out.endswith(SUFFIX)


def test_strip_suffix_handles_empty():
	assert strip_suffix(None) == ""


def test_hand_typed_capital_suffix_is_normalised():
	assert apply_suffix("Tomato (Kg) (Current)", 1) == "Tomato (Kg) (current)"
	assert apply_suffix("Tomato (Kg) (Current)", 0) == "Tomato (Kg)"
