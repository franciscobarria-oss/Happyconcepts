from happy_kitchen.hk_operations import email_card_rules as r


def test_health_off_and_incomplete():
	assert r.pickup_health(False, True, "", 1)[0] == "off"
	assert r.pickup_health(True, False, "", 1)[0] == "danger"


def test_health_error_beats_fresh_check():
	assert r.pickup_health(True, True, "Gmail answered 403.", 1)[0] == "danger"


def test_health_stale_and_never_checked():
	assert r.pickup_health(True, True, "", None)[0] == "warning"
	assert r.pickup_health(True, True, "", 61)[0] == "warning"
	assert r.pickup_health(True, True, "", 20)[0] == "ok"


def test_delivery_buckets():
	got = r.delivery_buckets(["2026-10-22", "2026-10-24", "2026-10-24", "2026-10-25", "2026-10-26", "2026-11-02", "", None], "2026-10-24")
	assert got == [{"key": "late", "count": 1}, {"key": "today", "count": 2}, {"key": "tomorrow", "count": 1},
	               {"key": "after", "count": 1}, {"key": "later", "count": 1}, {"key": "none", "count": 2}]


def test_delivery_buckets_empty_and_datetime_text():
	assert r.delivery_buckets([], "2026-10-24") == []
	assert r.delivery_buckets(["2026-10-24 00:00:00"], "2026-10-24") == [{"key": "today", "count": 1}]
