"""Per-site switch for the Happy Concepts desk theme (public/css/hk_theme.css) and the
EN / 中 language toggle (public/js/hk_theme.js).

The theme is on when Recipe Settings > "Happy Concepts desk theme" is ticked (patch
theme_defaults ticks it once on every site). `hk_theme` in site_config.json (1 or 0)
overrides it, e.g. to force it off on a test site."""

import frappe

from happy_kitchen.theme_rules import TOGGLE_LANGUAGES, theme_on, valid_language


def theme_enabled() -> bool:
	try:
		setting = frappe.db.get_single_value("Recipe Settings", "desk_theme")
	except Exception:
		setting = 0  # column not there yet (before migrate): stock look
	return theme_on(frappe.conf.get("hk_theme"), setting)


def boot_session(bootinfo):
	bootinfo.hk_theme = 1 if theme_enabled() else 0


@frappe.whitelist()
def set_language(lang: str) -> str:
	"""Switch the current user's desk language between English and Traditional Chinese."""
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in first."), frappe.PermissionError)
	if not valid_language(lang):
		frappe.throw(frappe._("Language must be one of: {0}").format(", ".join(TOGGLE_LANGUAGES)))
	frappe.db.set_value("User", frappe.session.user, "language", lang)
	frappe.clear_cache(user=frappe.session.user)
	return lang
