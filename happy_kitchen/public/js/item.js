// Item form: links to the supplier/recipe views, "Replace in recipes…" (hk_replace_ingredient.js) and the Label tab.
frappe.ui.form.on("Item", {
	refresh(frm) {
		hk_render_label(frm);
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

// Label tab: the product's label as it will print, what is still missing, and the "checked" sign-off.
function hk_render_label(frm) {
	const field = frm.fields_dict.hk_label_preview;
	if (!field) return;
	const $w = field.$wrapper;
	const esc = frappe.utils.escape_html;
	if (frm.is_new()) return $w.empty();

	if (!frm.doc.is_sales_item) {
		$w.html(`<div class="hk-label-hint text-muted" style="margin-bottom:12px">
			${__("This ingredient appears on product labels as <b>{0}</b>.", [esc(frm.doc.hk_label_name || frm.doc.item_name)])}
			<button class="btn btn-xs btn-default hk-suggest" style="margin-left:8px">${__("Suggest allergens")}</button>
		</div>`);
		$w.find(".hk-suggest").on("click", () => hk_suggest_allergens(frm));
		return;
	}

	$w.html(`<p class="text-muted">${__("Drawing the label...")}</p>`);
	frappe.call("happy_kitchen.hk_operations.labels.item_label_preview", { item_code: frm.doc.name }).then(({ message: m }) => {
		if (!m) return;
		const c = m.content;
		const tone = { Checked: "green", "Not checked": "orange", "Changed since check": "red" }[m.state.state] || "gray";
		const state_txt = {
			Checked: __("Label checked. Print labels from an order's Labels menu when you want them."),
			"Not checked": __("Not checked yet. Labels asked for on an order wait until a manager checks this label."),
			"Changed since check": __("The recipe, an ingredient or a label field changed since the last check. Labels wait until it is checked again."),
		}[m.state.state];
		const missing = m.state.missing.length
			? `<div class="alert alert-warning" style="margin-top:10px"><b>${__("Before it can be checked")}:</b><ul style="margin:6px 0 0 18px">${m.state.missing.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`
			: "";
		const rows = (c.ingredient_rows || [])
			.map((r) => `<tr><td>${esc(r.name)}</td><td class="text-right">${r.grams > 0 ? format_number(r.grams, null, 2) + " g" : "—"}</td>
				<td class="text-muted small">${r.items.map((i) => `<a href="/app/item/${encodeURIComponent(i)}">${esc(i)}</a>`).join(", ")}</td></tr>`)
			.join("");
		const check_btn = m.can_check && !m.state.missing.length && m.state.state !== "Checked"
			? `<button class="btn btn-primary btn-sm hk-check-label">${__("Mark label as checked")}</button>` : "";
		$w.html(`
			<div style="display:flex; gap:24px; flex-wrap:wrap; align-items:flex-start; margin-bottom:16px">
				<img src="data:image/png;base64,${m.png}" alt="" style="width:440px; max-width:100%; border:1px solid var(--border-color); border-radius:6px; background:#fff">
				<div style="flex:1; min-width:280px">
					<p><span class="indicator-pill ${tone}">${__(m.state.state)}</span></p>
					<p>${state_txt}</p>
					${missing}
					<p class="text-muted small">${__("Shelf life: {0} days (Inventory tab → Shelf Life In Days).", [c.shelf_life_days || 0])}
						${c.oem_spec ? " " + __("A client spec sheet may change shelf life and storage for that client.") : ""}</p>
					${check_btn}
					${c.recipe_item ? `<table class="table table-sm" style="margin-top:12px"><thead><tr><th>${__("Ingredient (heaviest first)")}</th><th class="text-right">${__("Per piece")}</th><th>${__("Items")}</th></tr></thead><tbody>${rows}</tbody></table>`
						: `<p class="text-muted">${__("No recipe found for this product. Link one with Made From Recipe on the Sales tab.")}</p>`}
				</div>
			</div>`);
		$w.find(".hk-check-label").on("click", () =>
			frappe.confirm(__("Have you read the whole label, including allergens, storage and shelf life, and is it correct?"), () =>
				frappe.call({
					method: "happy_kitchen.hk_operations.labels.mark_label_checked",
					args: { item_code: frm.doc.name },
					freeze: true,
				}).then(({ message }) => {
					frappe.show_alert({ message: __("Label checked. {0} waiting label job(s) sent to the printer.", [message.released]), indicator: "green" });
					frm.reload_doc();
				})
			)
		);
	});
}

function hk_suggest_allergens(frm) {
	frappe.call("happy_kitchen.hk_operations.labels.suggest_allergens", { item_code: frm.doc.name }).then(({ message }) => {
		const found = message || [];
		const have = (frm.doc.hk_allergens || []).map((r) => r.allergen);
		const add = found.filter((a) => !have.includes(a));
		if (!add.length) {
			frappe.msgprint(__("No allergen keywords found in the name. Check the supplier's pack or spec sheet."));
			return;
		}
		frm.set_value("hk_allergens", have.concat(add).map((a) => ({ allergen: a })));
		frappe.show_alert({ message: __("Suggested: {0}. Check the pack, then tick Allergens reviewed and save.", [add.join(", ")]), indicator: "orange" });
	});
}
