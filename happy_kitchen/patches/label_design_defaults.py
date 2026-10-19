import frappe

# Wording of the printed Happy Concepts labels (scan of 2026-10-14).
PHRASES = {
	"Gluten": "cereals containing gluten",
	"Crustaceans": "crustaceans",
	"Eggs": "eggs",
	"Fish": "fish",
	"Peanuts": "peanuts",
	"Soybeans": "soybeans",
	"Milk": "milk",
	"Tree nuts": "tree nuts",
	"Sulphites": "sulphites",
	"Sesame": "sesame",
}
DEFAULTS = {
	"maker_lines": "Happy Concepts Food Ltd.\nFlat D, 7/F, Derrick Industrial Building,\n49-51 Wong Chuk Hang Road, Hong Kong",
	"origin_line": "Made in Hong Kong",
	"default_note": "For immediate consumption after opening",
	"factory_statement": "Produced in a factory where tree nuts, fish, eggs, milk, peanuts, soybeans, crustaceans, "
	                     "cereals containing gluten and their products are also handled",
}


def execute():
	"""Label layout of the printed Happy Concepts labels: allergen wording, manufacturer,
	origin, note and factory statement. Only fills blanks, so edits are kept."""
	for name, phrase in PHRASES.items():
		if frappe.db.exists("Allergen", name) and not frappe.db.get_value("Allergen", name, "label_phrase"):
			frappe.db.set_value("Allergen", name, "label_phrase", phrase)
	settings = frappe.get_single("Label Settings")
	changed = False
	for field, value in DEFAULTS.items():
		if not settings.get(field):
			settings.set(field, value)
			changed = True
	if changed:
		settings.save(ignore_permissions=True)
