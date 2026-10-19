// "Replace in all recipes": swap one ingredient for another in every recipe that uses it.
// Opened from the Recipe form after an ingredient was changed and saved, and from the
// Item form (Actions > Replace in recipes...). Loaded on every desk page (hooks.app_include_js).
//
// hk_replace_ingredient({ old_item, new_item, exclude, source })
//   new_item given: the swap already happened in recipe `source`; only asks about the others.
//   new_item empty: asks which ingredient to use instead.
window.hk_replace_ingredient = async function ({ old_item, new_item, exclude, source }) {
	const API = "happy_kitchen.recipe_management.replace_ingredient.";
	const esc = frappe.utils.escape_html;
	const { recipes, archived } = await frappe.xcall(API + "recipes_using", { item_code: old_item, exclude });
	const [old_name, new_name] = await Promise.all(
		[old_item, new_item].map((i) => (i ? frappe.db.get_value("Item", i, "item_name").then((r) => r.message.item_name || i) : null))
	);
	if (!recipes.length) {
		if (!new_item) frappe.msgprint(__("{0} isn't used in any active recipe.", [esc(old_name)]));
		return;
	}
	const amount = (r) => r.lines.map((l) => `${format_number(l.qty, null, 2)} ${l.uom}`).join(" + ");
	const intro = new_item
		? __("You replaced <b>{0}</b> with <b>{1}</b>. {0} is also used in {2} other recipes. Replace it there too?", [esc(old_name), esc(new_name), recipes.length])
		: __("<b>{0}</b> is used in {1} recipes. Choose what to use instead and where.", [esc(old_name), recipes.length]);
	const d = new frappe.ui.Dialog({
		title: __("Replace in all recipes"),
		size: "large",
		fields: [
			{ fieldtype: "HTML", fieldname: "intro", options: `<p>${intro}</p>` },
			{
				// already chosen on the recipe (and named in the intro): no field to fill
				fieldtype: "Link", fieldname: "new_item", label: __("Replace with"), options: "Item",
				reqd: new_item ? 0 : 1, hidden: new_item ? 1 : 0,
				get_query: () => ({ filters: { disabled: 0, name: ["!=", old_item] } }),
			},
			{
				fieldtype: "Float", fieldname: "factor", label: __("Quantity factor"), default: 1, reqd: 1,
				description: __("Each recipe's quantity is multiplied by this. Keep 1 to use the same amount (e.g. 0.8 if the new product is stronger)."),
			},
			{ fieldtype: "Section Break", label: __("Recipes") },
			{
				fieldtype: "MultiCheck", fieldname: "recipes", columns: 2, select_all: true,
				options: recipes.map((r) => ({
					label: `${r.recipe_name || r.name} · ${amount(r)}${r.status !== "Active" ? ` (${__(r.status)})` : ""}`,
					value: r.name,
					checked: 1,
				})),
			},
			{
				fieldtype: "HTML", fieldname: "note",
				options: `<p class="text-muted small">${[
					archived ? __("{0} archived recipes are left as they were.", [archived]) : "",
					__("Each changed recipe is re-costed and gets a comment. Products with labels will need their label checked again."),
				].filter(Boolean).join(" ")}</p>`,
			},
		],
		primary_action_label: __("Replace in selected recipes"),
		primary_action: async (v) => {
			if (!v.recipes || !v.recipes.length) return frappe.msgprint(__("Tick at least one recipe."));
			d.disable_primary_action();
			let r;
			try {
				r = await frappe.xcall(API + "replace_in_recipes", {
					old_item, new_item: new_item || v.new_item, recipes: v.recipes, factor: v.factor, source: source || null,
				}, "POST");
			} catch (e) {
				d.enable_primary_action();
				return;
			}
			d.hide();
			const link = (n) => `<a href="/app/recipe/${encodeURIComponent(n)}">${esc(n)}</a>`;
			const parts = [`<p>${__("Replaced in {0} recipes.", [r.changed.length])}</p>`];
			if (r.failed.length)
				parts.push(`<p><b>${__("Not changed")}:</b></p><ul>${r.failed.map((f) => `<li>${link(f.recipe)}: ${esc(f.error)}</li>`).join("")}</ul>`);
			if (r.skipped.length)
				parts.push(`<p class="text-muted">${__("Skipped")}: ${r.skipped.map((s) => `${link(s.recipe)} (${esc(s.reason)})`).join(", ")}</p>`);
			frappe.msgprint({ title: __("Replace in all recipes"), message: parts.join(""), indicator: r.failed.length ? "orange" : "green" });
		},
		secondary_action_label: __("Not now"),
		secondary_action: () => d.hide(),
	});
	// resolves when the dialog closes, so several swaps are asked about one after another
	return new Promise((resolve) => {
		d.onhide = resolve;
		d.show();
	});
};
