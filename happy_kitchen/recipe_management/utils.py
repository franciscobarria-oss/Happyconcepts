import frappe

DEFAULT_PRIMARY = "#4472C4"
DEFAULT_ACCENT = "#FFF2CC"


def get_recipe_branding() -> dict:
	"""Branding for the A4 recipe print formats (Recipe Settings)."""
	s = frappe.get_cached_doc("Recipe Settings")
	return frappe._dict(
		brand_name=s.brand_name or "Happy Concepts",
		brand_logo=s.brand_logo,
		brand_tagline=s.brand_tagline,
		primary_color=s.primary_color or DEFAULT_PRIMARY,
		accent_color=s.accent_color or DEFAULT_ACCENT,
		print_footer=s.print_footer,
	)
