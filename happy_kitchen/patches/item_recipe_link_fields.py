from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Link a sales item to the recipe that makes it, for SKUs that aren't the
	recipe's own item (a customer's article number, a box of 200 pieces)."""
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "hk_recipe",
					"label": "Made From Recipe",
					"fieldtype": "Link",
					"options": "Recipe",
					"insert_after": "sales_uom",
					"description": "For sales items sold under another code than the recipe's own item, e.g. a customer's article number or a box.",
				},
				{
					"fieldname": "hk_recipe_qty",
					"label": "Recipe Units per Sales Unit",
					"fieldtype": "Float",
					"default": "1",
					"insert_after": "hk_recipe",
					"depends_on": "hk_recipe",
					"description": "How many of the recipe's yield units one of this item contains, e.g. 200 for a box of 200 dough pieces.",
				},
			]
		},
		update=True,
	)
