"""P13: theme flag in boot, EN / 中 toggle round trip, Chinese translations loaded. Rolled back."""

import frappe

from happy_kitchen import theme

USER = "e2e-theme@example.com"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	try:
		_check(frappe.db.exists("Language", "zh-TW"), "zh-TW language exists")
		_check("hk_theme.css" in " ".join(frappe.get_hooks("app_include_css")), "theme CSS in app_include_css")

		frappe.db.set_single_value("Recipe Settings", "desk_theme", 1)
		boot = frappe._dict()
		theme.boot_session(boot)
		forced = frappe.conf.get("hk_theme")
		_check(boot.hk_theme == (1 if forced is None else (1 if int(forced) else 0)), f"boot hk_theme {boot.hk_theme}")
		if forced is None:
			frappe.db.set_single_value("Recipe Settings", "desk_theme", 0)
			theme.boot_session(boot)
			_check(boot.hk_theme == 0, "theme off when unticked")

		frappe.get_doc({"doctype": "User", "email": USER, "first_name": "E2E Theme", "send_welcome_email": 0,
		                "language": "en"}).insert(ignore_permissions=True)
		frappe.set_user(USER)
		_check(theme.set_language("zh-TW") == "zh-TW", "set_language returns the language")
		_check(frappe.db.get_value("User", USER, "language") == "zh-TW", "user language is zh-TW")
		try:
			theme.set_language("fr")
			raise AssertionError("fr must be refused")
		except frappe.ValidationError:
			pass
		theme.set_language("en")
		_check(frappe.db.get_value("User", USER, "language") == "en", "back to English")
		frappe.set_user("Administrator")

		from frappe.translate import get_all_translations

		zh = get_all_translations("zh-TW")
		for en in ("Stock Take", "Wastage Log", "Clock In", "Overtime Entry"):
			_check(zh.get(en), f"zh-TW translation for {en!r}")
		print("ok: theme e2e passed")
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()
