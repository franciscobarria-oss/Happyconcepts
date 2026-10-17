// Item form: links to the supplier/recipe views and "Replace in recipes…" (hk_replace_ingredient.js).
frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Supplier Prices & Recipes"),
			() => frappe.set_route("query-report", "Ingredients and Packaging by Supplier", { item: frm.doc.name }),
			__("View")
		);
		if (frm.doc.is_stock_item && frappe.model.can_write("Recipe"))
			frm.add_custom_button(
				__("Replace in recipes…"),
				() => hk_replace_ingredient({ old_item: frm.doc.name }),
				__("Actions")
			);
		frappe.db.get_value("Recipe", { item: frm.doc.name }, "name").then(({ message }) => {
			if (message && message.name)
				frm.add_custom_button(__("Recipe"), () => frappe.set_route("Form", "Recipe", message.name), __("View"));
		});
	},
});
