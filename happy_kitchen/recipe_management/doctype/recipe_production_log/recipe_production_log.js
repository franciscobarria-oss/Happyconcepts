// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.ui.form.on("Recipe Production Log", {
	setup(frm) {
		frm.set_query("recipe", "items", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(__("Ingredient Usage"), () =>
			frappe.set_route("query-report", "Recipe Ingredient Usage", {
				source: "Production Log",
				from_date: frm.doc.posting_date,
				to_date: frm.doc.posting_date,
				warehouse: frm.doc.warehouse,
			})
		);
		const M = "happy_kitchen.recipe_management.doctype.recipe_production_log.recipe_production_log.";
		if (!frm.doc.batch_stock_entries) {
			frm.add_custom_button(__("Add Batch Preparations to Stock"), () =>
				frm.call({ method: M + "make_batch_preparation_entries", args: { name: frm.doc.name }, freeze: true }).then((r) => {
					const names = r.message || [];
					if (!names.length) frappe.msgprint(__("This log has no Batch Preparation recipes."));
					else if (names.length === 1) frappe.set_route("Form", "Stock Entry", names[0]);
					else frappe.set_route("List", "Stock Entry", { name: ["in", names] });
					frm.reload_doc();
				})
			);
		}
		if (!frm.doc.stock_entry) {
			frm.add_custom_button(__("Create Material Issue"), () =>
				frm
					.call({
						method: "happy_kitchen.recipe_management.doctype.recipe_production_log.recipe_production_log.make_stock_entry",
						args: { name: frm.doc.name },
						freeze: true,
					})
					.then((r) =>
						r.message
							? frappe.set_route("Form", "Stock Entry", r.message)
							: frappe.msgprint(__("No ingredients to issue: this log only has Batch Preparation recipes."))
					)
			);
		}
	},
});
