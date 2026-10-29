// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Take Sheet", {
	setup(frm) {
		frm.set_query("storage_area", "items", () => ({ filters: { is_group: 0, company: frm.doc.company } }));
		frm.set_query("item", "items", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Add all stocked ingredients"), () =>
			frm
				.call({
					method: "happy_kitchen.recipe_management.doctype.stock_take_sheet.stock_take_sheet.add_stocked_ingredients",
					args: { sheet: frm.doc.name },
					freeze: true,
				})
				.then((r) => {
					frappe.show_alert({ message: __("{0} ingredients added", [r.message || 0]), indicator: "green" });
					frm.reload_doc();
				})
		);
		frm.add_custom_button(__("Fill pack sizes from items"), () => {
			if (frm.is_dirty()) return frappe.msgprint(__("Save the sheet first."));
			const run = (overwrite) =>
				frm
					.call({
						method: "happy_kitchen.recipe_management.doctype.stock_take_sheet.stock_take_sheet.fill_pack_sizes",
						args: { sheet: frm.doc.name, overwrite },
						freeze: true,
					})
					.then(({ message: m }) => {
						frappe.msgprint(
							__("Pack sizes set on {0} ingredients.", [m.filled]) +
								(m.no_packs ? "<br>" + __("{0} ingredients have no pack size on their Item yet, so they are counted in loose units only.", [m.no_packs]) : "")
						);
						frm.reload_doc();
					});
			frappe.prompt(
				{
					fieldname: "overwrite",
					fieldtype: "Check",
					label: __("Also replace pack sizes that are already set"),
					description: __("Takes up to 3 pack sizes from each item's units of measure, biggest first. Rows without pack sizes are always filled."),
				},
				(v) => run(v.overwrite ? 1 : 0),
				__("Fill pack sizes from items"),
				__("Fill")
			);
		});
		frm.add_custom_button(__("Print Count Sheet"), () =>
			window.open(`/api/method/happy_kitchen.recipe_management.count_print.sheet?sheet=${encodeURIComponent(frm.doc.name)}`)
		);
		frm.add_custom_button(__("Start Stock Take"), () => {
			if (frm.is_dirty()) return frappe.msgprint(__("Save the sheet first."));
			frm
				.call({
					method: "happy_kitchen.recipe_management.doctype.stock_take.stock_take.make_stock_take",
					args: { sheet: frm.doc.name },
					freeze: true,
				})
				.then((r) => r.message && frappe.set_route("stock-take-count", r.message));
		});
	},
});
