"""Pure rules for the desk theme and the EN / 中 toggle (tests/test_theme.py)."""

# Traditional Chinese, as used in Hong Kong.
TOGGLE_LANGUAGES = ("en", "zh-TW")


def _flag(value) -> bool:
	try:
		return bool(int(value or 0))
	except (TypeError, ValueError):
		return str(value).strip().lower() in ("true", "yes", "on")


def theme_on(forced, setting) -> bool:
	"""site_config `hk_theme` (1 / 0) wins over Recipe Settings > desk_theme."""
	if forced is not None:
		return _flag(forced)
	return _flag(setting)


def valid_language(lang) -> bool:
	return lang in TOGGLE_LANGUAGES
