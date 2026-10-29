"""Pure rules for the "Current" marker on repeated purchase items (no Frappe import; tests/test_current_flag.py).

Several items can be the same product bought from different suppliers or in different packs
(e.g. Tomato by the kg, Tomato in tins). The one bought last is ticked "Current purchase" and its
name ends in " (current)" so it stands out on stock take sheets."""

SUFFIX = " (current)"
MAX_NAME = 140


def strip_suffix(name: str) -> str:
	"""Removes the ending in any capitalisation ("(Current)" was typed by hand once)."""
	name = (name or "").rstrip()
	while name.lower().endswith(SUFFIX):
		name = name[: -len(SUFFIX)].rstrip()
	return name


def apply_suffix(name: str, is_current) -> str:
	"""The item name with " (current)" added when ticked and removed when not (never twice)."""
	base = strip_suffix((name or "").rstrip())
	if not is_current:
		return base
	return base[: MAX_NAME - len(SUFFIX)] + SUFFIX
