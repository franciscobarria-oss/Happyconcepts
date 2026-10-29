// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

frappe.ui.form.on("Recipe", {
	setup(frm) {
		frm.set_query("supplier", "ingredients", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "happy_kitchen.recipe_management.api.supplier_query",
				filters: { item_code: row.item },
			};
		});
		frm.set_query("item", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
	},

	refresh(frm) {
		hk_render_cost_card(frm);
		// ingredients as saved, to notice a swapped ingredient (see after_save; the
		// swaps themselves are kept until after_save uses them, whichever runs first)
		frm.hk_saved_items = Object.fromEntries((frm.doc.ingredients || []).map((r) => [r.name, r.item]));
		if (frm.is_new()) return;

		frm.add_custom_button(__("Refresh Prices"), () => frm.save(), __("Costing"));
		frm.add_custom_button(
			__("Cost Analysis"),
			() => frappe.set_route("query-report", "Recipe Cost Analysis", { recipe: frm.doc.name }),
			__("Costing")
		);
		frm.add_custom_button(
			__("Ingredients & Packaging by Supplier"),
			() => frappe.set_route("query-report", "Ingredients and Packaging by Supplier", { recipe: frm.doc.name }),
			__("Costing")
		);
		frm.add_custom_button(
			__("Ingredient Usage"),
			() =>
				frappe.prompt(
					{ fieldname: "batches", fieldtype: "Float", label: __("Batches"), default: 1, reqd: 1 },
					(v) =>
						frappe.set_route("query-report", "Recipe Ingredient Usage", {
							recipe: frm.doc.name,
							planned_batches: v.batches,
						}),
					__("Usage for how many batches?")
				),
			__("Production")
		);
		frm.add_custom_button(
			__("Log Production"),
			() =>
				frappe.new_doc("Recipe Production Log", {}, (log) => {
					const row = frappe.model.add_child(log, "items");
					frappe.model.set_value(row.doctype, row.name, "recipe", frm.doc.name);
				}),
			__("Production")
		);

		if (frm.doc.missing_price_count) {
			frm.dashboard.set_headline_alert(
				__("{0} ingredient line(s) have no buying price. Their cost counts as 0.", [
					frm.doc.missing_price_count,
				]),
				"orange"
			);
		}
	},
});

frappe.ui.form.on("Recipe Ingredient", {
	item(frm, cdt, cdn) {
		// a new ingredient: let the server pick its cheapest supplier on save
		frappe.model.set_value(cdt, cdn, "supplier", null);
		const was = (frm.hk_saved_items || {})[cdn];
		const now = locals[cdt][cdn].item;
		if (!frm.hk_swaps) frm.hk_swaps = {};
		if (was && now && was !== now) frm.hk_swaps[was] = now;
		else if (was) delete frm.hk_swaps[was];
	},
});

// After a save that swapped an ingredient, offer the same swap in the other recipes.
frappe.ui.form.on("Recipe", {
	onload(frm) {
		frm.hk_swaps = {};
	},
	async after_save(frm) {
		const swaps = Object.entries(frm.hk_swaps || {});
		frm.hk_swaps = {};
		const items = new Set((frm.doc.ingredients || []).map((r) => r.item));
		for (const [old_item, new_item] of swaps) {
			if (!items.has(new_item)) continue;
			await hk_replace_ingredient({ old_item, new_item, exclude: frm.doc.name, source: frm.doc.name });
		}
	},
});

// Cost card at the top of the form: the numbers people look for first.
let hk_target_food_cost = null;

async function hk_render_cost_card(frm) {
	const field = frm.fields_dict.cost_card;
	if (!field) return;
	if (frm.is_new()) {
		field.$wrapper.html(`<div class="text-muted small">${__("Costs appear after the first save.")}</div>`);
		return;
	}
	if (hk_target_food_cost === null) {
		hk_target_food_cost = flt(await frappe.db.get_single_value("Recipe Settings", "target_food_cost_pct")) || 30;
	}
	const d = frm.doc;
	const cur = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"), 2);
	const pct = (v) => (v || v === 0 ? `${flt(v, 1)}%` : "–");
	const tone = (v, target) => (!v ? "" : v <= target ? "hk-good" : v <= target + 10 ? "hk-warn" : "hk-bad");
	const has_price = flt(d.selling_price) > 0;
	const card = (label, value, cls = "", sub = "") =>
		`<div class="hk-cc-card ${cls}"><div class="hk-cc-label">${label}</div><div class="hk-cc-value">${value}</div>${sub ? `<div class="hk-cc-sub">${sub}</div>` : ""}</div>`;
	const chips = [];
	if (d.status === "Archived") chips.push(`<span class="hk-cc-chip hk-bad">${__("Archived")}</span>`);
	if (d.missing_price_count) chips.push(`<span class="hk-cc-chip hk-warn">${__("{0} ingredient(s) without a price", [d.missing_price_count])}</span>`);
	if (!has_price && d.recipe_type === "Finished Product") chips.push(`<span class="hk-cc-chip hk-warn">${__("No selling price")}</span>`);

	field.$wrapper.html(`
		<style>
			.hk-cc { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 8px; }
			.hk-cc-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 14px; background: var(--card-bg); }
			.hk-cc-label { font-size: 12px; color: var(--text-muted); }
			.hk-cc-value { font-size: 22px; font-weight: 700; line-height: 1.3; }
			.hk-cc-sub { font-size: 12px; color: var(--text-muted); }
			.hk-cc-card.hk-good { border-color: var(--hk-success, var(--green-400, #48bb78)); background: var(--hk-success-soft, var(--green-50, #f0fff4)); }
			.hk-cc-card.hk-warn { border-color: var(--hk-warning, var(--orange-400, #ed8936)); background: var(--hk-warning-soft, var(--orange-50, #fffaf0)); }
			.hk-cc-card.hk-bad { border-color: var(--hk-danger, var(--red-400, #f56565)); background: var(--hk-danger-soft, var(--red-50, #fff5f5)); }
			.hk-cc-meta { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
			.hk-cc-chip { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 10px; margin-right: 6px; }
			.hk-cc-chip.hk-warn { background: var(--hk-warning-soft, var(--orange-100, #feebc8)); } .hk-cc-chip.hk-bad { background: var(--hk-danger-soft, var(--red-100, #fed7d7)); }
		</style>
		${chips.length ? `<div style="margin-bottom:8px">${chips.join("")}</div>` : ""}
		<div class="hk-cc">
			${card(__("Cost per unit"), cur(d.cost_per_unit), "", __("ingredients {0}", [cur(d.ingredient_cost_per_unit)]))}
			${card(__("Selling price"), has_price ? cur(d.selling_price) : "–")}
			${card(__("Food cost"), has_price ? pct(d.food_cost_pct) : "–", has_price ? tone(d.food_cost_pct, hk_target_food_cost) : "", __("target {0}%", [hk_target_food_cost]))}
			${card(__("Total cost"), has_price ? pct(d.total_cost_pct) : "–")}
			${card(__("Margin per unit"), has_price ? cur(d.gross_margin) : "–", has_price ? (flt(d.gross_margin) > 0 ? "" : "hk-bad") : "")}
		</div>
		<div class="hk-cc-meta">
			${__("Per batch")}: <b>${format_number(d.batch_yield || 0, null, 0)} ${frappe.utils.escape_html(d.yield_uom || "")}</b>
			· ${__("batch cost")} ${cur(d.total_batch_cost)}
			· ${__("ingredients")} ${cur(d.total_ingredient_cost)} · ${__("labour")} ${cur(d.total_labour_cost)} · ${__("overheads")} ${cur(d.total_overhead_cost)}
			${d.suggested_price ? `· ${__("suggested price")} ${cur(d.suggested_price)}` : ""}
		</div>`);
}
