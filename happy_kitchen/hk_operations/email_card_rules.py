"""Pure rules for the "Email orders" card on Today (no frappe, tested in tests/test_email_card.py)."""

from __future__ import annotations

from datetime import date, timedelta

STALE_MINUTES = 60  # the pick-up runs every 15 minutes: an hour without a check means something is wrong


def pickup_health(enabled: bool, complete: bool, last_error: str | None, minutes_since_check: float | None) -> tuple[str, str]:
	"""(tone, message) for the pick-up. Tone is off / ok / warning / danger."""
	if not enabled:
		return "off", "Gmail pick-up is switched off"
	if not complete:
		return "danger", "Gmail Settings is missing the Google sign-in"
	if last_error:
		return "danger", "The last check failed"
	if minutes_since_check is None:
		return "warning", "Not checked yet"
	if minutes_since_check > STALE_MINUTES:
		return "warning", "Not checked for over an hour"
	return "ok", "Checked mail a moment ago" if minutes_since_check < 2 else "Checked for new mail"


def delivery_buckets(dates: list, today: str) -> list[dict]:
	"""Draft orders by delivery day: Late, Today, Tomorrow, Day after, Later, No date (empty buckets left out)."""
	t = date.fromisoformat(today)
	tomorrow, after = t + timedelta(days=1), t + timedelta(days=2)
	order = ["late", "today", "tomorrow", "after", "later", "none"]
	counts = dict.fromkeys(order, 0)
	for d in dates:
		if not d:
			counts["none"] += 1
			continue
		d = date.fromisoformat(str(d)[:10])
		key = "late" if d < t else "today" if d == t else "tomorrow" if d == tomorrow else "after" if d == after else "later"
		counts[key] += 1
	return [{"key": k, "count": counts[k]} for k in order if counts[k]]
