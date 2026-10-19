import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Hong Kong's allergen list (Food and Drugs (Composition and Labelling) Regulations,
# Cap. 132W), plus sesame. Keywords only suggest; a person reviews each ingredient.
ALLERGENS = [
	("Gluten", "麩質", "flour\nwheat\nbread\nbarley\nrye\noat\nspelt\nmalt\nsemolina\nbiscuit\ncookie\nwafer\ntortilla\n"
	                  "lady finger\nsponge\ncake base\ntart shell\ncone\nnoodle\npasta\ncrumb\npanko\nsoy sauce\n麵粉\n小麥"),
	("Crustaceans", "甲殼類動物", "shrimp\nprawn\ncrab\nlobster\ncrayfish\n蝦\n蟹"),
	("Eggs", "蛋", "egg\nmayonnaise\nmeringue\n蛋"),
	("Fish", "魚", "fish\nanchovy\ntuna\nsalmon\ncod\n魚"),
	("Peanuts", "花生", "peanut\ngroundnut\n花生"),
	("Soybeans", "大豆", "soy\nsoya\ntofu\nedamame\nmiso\nlecithin\n豆腐\n大豆"),
	("Milk", "奶", "milk\nbutter\ncream\ncheese\nyogurt\nyoghurt\nwhey\nlactose\ncasein\nmascarpone\nricotta\n"
	               "condensed\nnutella\nwhite chocolate\nmilk chocolate\nhorlicks\nghee\n奶\n牛油\n芝士"),
	("Tree nuts", "木本堅果", "almond\nhazelnut\nwalnut\ncashew\npecan\npistachio\nmacadamia\nbrazil nut\npine nut\n"
	                      "praline\nnutella\nmarzipan\n杏仁\n榛子\n核桃"),
	("Sulphites", "亞硫酸鹽", "sulphite\nsulfite\ndried apricot\nraisin\nwine"),
	("Sesame", "芝麻", "sesame\ntahini\n芝麻"),
]


def _before_connections_tab() -> str:
	"""The last Item field before the Connections tab, so the Label tab sits just before it."""
	fields = [f.fieldname for f in frappe.get_meta("Item").fields]
	if "dashboard_tab" in fields:
		i = fields.index("dashboard_tab")
		return fields[i - 1]
	return fields[-1]


def execute():
	"""Product labels printed on a Raspberry Pi label printer when a sales order is submitted."""
	if not frappe.db.exists("Role", "Label Printer"):
		frappe.get_doc({"doctype": "Role", "role_name": "Label Printer", "desk_access": 0}).insert(ignore_permissions=True)

	for n, (name, zh, keywords) in enumerate(ALLERGENS, start=1):
		if not frappe.db.exists("Allergen", name):
			frappe.get_doc({"doctype": "Allergen", "allergen_name": name, "allergen_zh": zh,
			                "keywords": keywords, "sort_order": n}).insert(ignore_permissions=True)

	anchor = _before_connections_tab()
	if anchor.startswith("hk_label"):
		anchor = "hk_label_tab"
	create_custom_fields(
		{
			"Item": [
				{"fieldname": "hk_label_tab", "label": "Label", "fieldtype": "Tab Break", "insert_after": anchor},
				{"fieldname": "hk_label_preview", "label": "Label preview", "fieldtype": "HTML", "insert_after": "hk_label_tab"},
				# as an ingredient of other products
				{"fieldname": "hk_ingredient_section", "label": "On other products' labels", "fieldtype": "Section Break",
				 "insert_after": "hk_label_preview", "depends_on": "eval:doc.is_purchase_item"},
				{"fieldname": "hk_label_name", "label": "Name in ingredient lists", "fieldtype": "Data",
				 "insert_after": "hk_ingredient_section",
				 "description": "What customers read, without brand or pack size, e.g. Wheat flour, Unsalted butter. Blank = item name."},
				{"fieldname": "hk_allergens_checked", "label": "Allergens reviewed", "fieldtype": "Check",
				 "insert_after": "hk_label_name",
				 "description": "Tick after checking the allergens against the supplier's pack or spec sheet, even if there are none."},
				{"fieldname": "hk_ingredient_cb", "fieldtype": "Column Break", "insert_after": "hk_allergens_checked"},
				{"fieldname": "hk_allergens", "label": "Allergens", "fieldtype": "Table MultiSelect", "options": "Item Allergen",
				 "insert_after": "hk_ingredient_cb"},
				# as a product we sell
				{"fieldname": "hk_product_label_section", "label": "Product label", "fieldtype": "Section Break",
				 "insert_after": "hk_allergens", "depends_on": "eval:doc.is_sales_item"},
				{"fieldname": "hk_label_title", "label": "Product name on label", "fieldtype": "Data",
				 "insert_after": "hk_product_label_section", "description": "Blank = item name."},
				{"fieldname": "hk_storage", "label": "Storage", "fieldtype": "Select", "options": "\nAmbient\nChilled\nFrozen",
				 "insert_after": "hk_label_title"},
				{"fieldname": "hk_net_weight_g", "label": "Net weight per piece (g)", "fieldtype": "Float",
				 "insert_after": "hk_storage", "description": "Blank = the recipe's unit weight."},
				{"fieldname": "hk_units_per_label", "label": "Pieces per label", "fieldtype": "Int", "default": "1",
				 "insert_after": "hk_net_weight_g",
				 "description": "1 = a label on every piece. 48 = one label per carton of 48; an order of 200 prints 4 × 48 and 1 × 8."},
				{"fieldname": "hk_product_label_cb", "fieldtype": "Column Break", "insert_after": "hk_units_per_label"},
				{"fieldname": "hk_label_note", "label": "Extra line on label", "fieldtype": "Small Text",
				 "insert_after": "hk_product_label_cb", "description": "e.g. May contain traces of nuts. / Heat before serving."},
				{"fieldname": "hk_no_label", "label": "Don't print labels for this item", "fieldtype": "Check",
				 "insert_after": "hk_label_note", "description": "For delivery charges, services and other non-food lines."},
				{"fieldname": "hk_label_checked", "label": "Label checked", "fieldtype": "Check", "read_only": 1,
				 "insert_after": "hk_no_label", "no_copy": 1},
				{"fieldname": "hk_label_checked_by", "label": "Checked by", "fieldtype": "Link", "options": "User",
				 "read_only": 1, "insert_after": "hk_label_checked", "no_copy": 1, "depends_on": "hk_label_checked"},
				{"fieldname": "hk_label_checked_on", "label": "Checked on", "fieldtype": "Datetime", "read_only": 1,
				 "insert_after": "hk_label_checked_by", "no_copy": 1, "depends_on": "hk_label_checked"},
				{"fieldname": "hk_label_signature", "label": "Checked label fingerprint", "fieldtype": "Data", "hidden": 1,
				 "read_only": 1, "insert_after": "hk_label_checked_on", "no_copy": 1},
			]
		},
		update=True,
	)

	settings = frappe.get_single("Label Settings")
	if not settings.date_basis:
		settings.create_on_submit = 1
		settings.date_basis = "Print date"
		settings.save(ignore_permissions=True)
