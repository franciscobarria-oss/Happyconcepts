from datetime import date

from happy_kitchen.hk_operations.order_stage import deliver_blocker, stage

T = date(2026, 10, 29)


def test_draft_is_confirmed_next():
	s = stage(0, "Draft")
	assert s["stage"] == "Draft" and s["next"] == "confirm"


def test_submitted_is_confirmed_and_late_after_delivery_day():
	assert stage(1, "To Deliver and Bill", 0, 0, "2026-10-29", T) == {
		"stage": "Confirmed", "color": "blue", "late": False, "next": "deliver", "part_delivered": False}
	s = stage(1, "To Deliver and Bill", 40, 0, "2026-10-24", T)
	assert s["late"] and s["color"] == "red" and s["part_delivered"]


def test_delivered_is_completed_with_or_without_invoice():
	assert stage(1, "To Bill", 100, 0)["stage"] == "Completed"
	assert stage(1, "To Bill", 100, 0)["invoiced"] is False
	assert stage(1, "Completed", 100, 100)["invoiced"] is True
	assert stage(1, "Completed", 0, 100)["stage"] == "Completed"  # skip-delivery orders


def test_hold_and_cancelled_keep_erpnext_state_closed_is_completed():
	assert stage(1, "On Hold")["stage"] == "On Hold"
	assert stage(1, "Closed", 50)["stage"] == "Completed"
	assert stage(1, "Closed", 0)["no_delivery_note"] is True
	assert stage(1, "Closed", 100)["no_delivery_note"] is False
	assert stage(2, "Cancelled")["next"] is None


def test_deliver_blocker():
	assert deliver_blocker(1, "To Deliver and Bill", 0) is None
	assert deliver_blocker(0, "Draft", 0)
	assert deliver_blocker(1, "On Hold", 0)
	assert deliver_blocker(1, "To Bill", 100)
	assert deliver_blocker(1, "Closed", 0)
	assert "revision" in deliver_blocker(1, "To Deliver", 0, needs_review=1)
