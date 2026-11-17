from happy_kitchen.hk_operations.auto_complete import is_due

T = "2026-11-18"


def test_due_the_day_after_delivery_date():
	assert is_due(1, "To Deliver and Bill", 0, 0, "2026-11-17", T)
	assert not is_due(1, "To Deliver and Bill", 0, 0, "2026-11-18", T)  # still going out today
	assert not is_due(1, "To Deliver and Bill", 0, 0, "2026-11-19", T)


def test_people_cases_are_left_alone():
	assert not is_due(0, "Draft", 0, 0, "2026-11-10", T)  # draft
	assert not is_due(1, "On Hold", 0, 0, "2026-11-10", T)
	assert not is_due(1, "To Bill", 0, 1, "2026-11-10", T)  # revised, not checked
	assert not is_due(1, "Closed", 0, 0, "2026-11-10", T)
	assert not is_due(1, "Completed", 100, 0, "2026-11-10", T)
	assert not is_due(1, "To Deliver and Bill", 0, 0, None, T)
