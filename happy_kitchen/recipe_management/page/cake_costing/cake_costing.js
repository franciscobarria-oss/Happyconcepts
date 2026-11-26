// Copyright (c) 2026, Happy Kitchen and contributors
// Cake costing on a phone: photo, size, ingredients, cost. Every Next tap saves the record, so staff can come back to it.
(() => {
const API = "happy_kitchen.recipe_management.cake_costing.";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const cur = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"), 2);
const STEPS = ["Photo", "Size", "Ingredients", "Cost"];

function css() {
	if (document.getElementById("hkcc-css")) return;
	$(`<style id="hkcc-css">
	.hkcc { max-width: 560px; width: 100%; box-sizing: border-box; margin: 0 auto; padding-bottom: 80px; }
	.hkcc-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px; background: var(--card-bg); margin-bottom: 12px; }
	.hkcc-in { min-height: 48px; font-size: 17px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border-color); background: var(--control-bg); width: 100%; }
	.hkcc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
	.hkcc-grid label { font-size: 12px; color: var(--text-muted); }
	.hkcc-steps { display: flex; gap: 6px; margin-bottom: 12px; } .hkcc-steps i { flex: 1; height: 5px; border-radius: 3px; background: var(--border-color); } .hkcc-steps i.on { background: var(--primary); }
	.hkcc-photo { width: 100%; max-height: 300px; object-fit: cover; border-radius: 10px; margin-bottom: 10px; }
	.hkcc-row { border-bottom: 1px solid var(--border-color); padding: 8px 0; margin-bottom: 4px; }
	.hkcc-row.assumed { background: #fff1d6; border-radius: 8px; padding: 8px; }
	.hkcc-r2 { display: grid; grid-template-columns: 1fr 84px 1fr 84px; gap: 6px; align-items: end; margin-top: 6px; }
	.hkcc-r2 label { font-size: 11px; color: var(--text-muted); display: block; }
	.hkcc-r2 .hkcc-in { min-height: 40px; font-size: 15px; padding: 4px 8px; }
	.hkcc-calc { font-size: 12px; color: var(--text-muted); margin-top: 4px; display: flex; justify-content: space-between; align-items: center; }
	.hkcc-big { width: 100%; min-height: 54px; font-size: 18px; border-radius: 12px; margin-top: 8px; }
	.hkcc-tot { font-size: 34px; font-weight: 700; }
	.hkcc-flag { background: var(--hk-warning-soft, #feebc8); border-radius: 8px; padding: 2px 8px; font-size: 12px; margin-left: 4px; }
	.hkcc-t td { padding: 6px 0; border-bottom: 1px solid var(--border-color); } .hkcc-t td:last-child { text-align: right; }
	.hkcc input, .hkcc select { max-width: 100%; box-sizing: border-box; min-width: 0; }
	@media (max-width: 480px) { .hkcc-r2, .hkcc-r2[style] { grid-template-columns: 1fr 1fr !important; } .hkcc-grid { grid-template-columns: 1fr 1fr; } .hkcc-tot { font-size: 28px; } }
	@media (min-width: 768px) { .hkcc { max-width: 860px; } .hkcc-row { padding: 10px 4px; } }
	</style>`).appendTo("head");
}

frappe.pages["cake-costing"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Cake Costing"), single_column: true });
	css();
	wrapper.hkcc = new CakeCosting(wrapper);
};
frappe.pages["cake-costing"].on_page_show = (wrapper) => wrapper.hkcc.home();

class CakeCosting {
	constructor(wrapper) { this.$b = $(wrapper).find(".layout-main-section"); this.d = null; this.step = 0; }
	async home() {
		const rows = await frappe.xcall(API + "recent");
		this.$b.html(`<div class="hkcc"><button class="btn btn-primary hkcc-big hkcc-new">${__("New cake")}</button>
			<h5 style="margin:16px 0 8px">${__("Saved cakes")}</h5>
			${rows.map((r) => `<div class="hkcc-card hkcc-open" data-n="${esc(r.name)}" style="cursor:pointer"><b>${esc(r.cake_name)}</b>
			<span class="text-muted"> · ${__(r.step)} · ${cur(r.total_cost)}</span><br><small class="text-muted">${esc(r.name)}</small></div>`).join("") || `<p class="text-muted">${__("No cakes saved yet")}</p>`}</div>`);
		this.$b.find(".hkcc-new").on("click", () => { this.d = { ingredients: [] }; this.step = 0; this.draw(); });
		this.$b.find(".hkcc-open").on("click", async (e) => {
			this.d = await frappe.xcall(API + "load", { name: $(e.currentTarget).data("n") });
			this.step = Math.max(0, STEPS.indexOf(this.d.step)); this.draw();
		});
	}
	async save(step) {
		this.collect();
		this.d = await frappe.xcall(API + "save_step", { data: this.d, name: this.d.name || null, step });
		frappe.show_alert({ message: __("Saved"), indicator: "green" }, 2);
	}
	collect() {
		const $b = this.$b;
		const v = (f) => $b.find(`[data-f="${f}"]`);
		["cake_name", "shape", "height_cm", "width_cm", "length_cm", "weight_g", "slices", "piece_weight_g", "labour_cost", "packaging_cost", "notes"].forEach((f) => {
			if (v(f).length) this.d[f] = v(f).val();
		});
		if ($b.find(".hkcc-row").length) {
			this.d.ingredients = $b.find(".hkcc-row").map((i, el) => {
				const $e = $(el), x = (k) => $e.find(`[data-k="${k}"]`);
				return {
					item: $e.data("item") || null, item_name: x("n").val(), qty_g: Number(x("q").val()) || 0, qty_unit: x("qu").val(), piece_g: Number(x("pg").val()) || 0,
					bulk_price: Number(x("bp").val()) || 0, pack_size: Number(x("ps").val()) || 0, pack_unit: x("pu").val(),
					price_source: $e.data("typed") ? "Typed" : "ERP", assumed: x("as").is(":checked") ? 1 : 0, ai_guess: $e.data("ai") ? 1 : 0,
				};
			}).get().filter((r) => r.item_name || r.item);
		}
	}
	nav(back, next) {
		return `<div style="display:flex;gap:8px">${back ? `<button class="btn btn-default hkcc-big hkcc-back">${__("Back")}</button>` : ""}
			<button class="btn btn-primary hkcc-big hkcc-next">${next}</button></div><button class="btn btn-link hkcc-home">${__("Saved cakes")}</button>`;
	}
	draw() {
		const d = this.d, s = this.step;
		const bar = `<div class="hkcc-steps">${STEPS.map((x, i) => `<i class="${i <= s ? "on" : ""}"></i>`).join("")}</div><h5>${s + 1}. ${__(STEPS[s])}</h5>`;
		let body = "";
		if (s === 0) body = `<div class="hkcc-card"><input class="hkcc-in" data-f="cake_name" placeholder="${__("Cake name")}" value="${esc(d.cake_name)}">
			${d.photo ? `<img class="hkcc-photo" src="${esc(d.photo)}" style="margin-top:10px">` : ""}
			<button class="btn btn-default hkcc-big hkcc-photo-btn">${d.photo ? __("Change photo") : __("Take or upload photo")}</button></div>`;
		if (s === 1) body = `<div class="hkcc-card"><select class="hkcc-in" data-f="shape">${["Round", "Square", "Loaf"].map((x) => `<option value="${x}" ${d.shape === x ? "selected" : ""}>${__(x)}</option>`).join("")}</select>
			<div class="hkcc-grid" style="margin-top:10px">
			<div><label>${__("Height (cm)")}</label><input class="hkcc-in" type="number" inputmode="decimal" data-f="height_cm" value="${d.height_cm || ""}"></div>
			<div><label>${__("Width (cm)")}</label><input class="hkcc-in" type="number" inputmode="decimal" data-f="width_cm" value="${d.width_cm || ""}"></div>
			<div><label>${__("Weight (g)")}</label><input class="hkcc-in" type="number" inputmode="decimal" data-f="weight_g" value="${d.weight_g || ""}"></div>
			<div><label>${__("Length (cm)")}</label><input class="hkcc-in" type="number" inputmode="decimal" data-f="length_cm" value="${d.length_cm || ""}"></div>
			<div><label>${__("Slices")}</label><input class="hkcc-in" type="number" data-f="slices" value="${d.slices || ""}"></div></div>
			<p class="text-muted" style="margin-top:8px">${d.volume_cm3 ? __("Volume {0} cm³", [Math.round(d.volume_cm3)]) : ""}</p></div>`;
		if (s === 2) body = `<div class="hkcc-card"><button class="btn btn-default hkcc-big hkcc-guess" style="margin-top:0">${__("Guess from photo")}</button>
			<div class="hkcc-lines" style="margin-top:10px">${(d.ingredients || []).map((r) => this.line(r)).join("")}</div>
			<button class="btn btn-default hkcc-big hkcc-add">${__("Add ingredient")}</button></div>`;
		if (s === 3) body = this.cost_html();
		this.$b.html(`<div class="hkcc">${bar}${body}${this.nav(s > 0, s === 3 ? __("Save") : __("Next"))}</div>`);
		this.bind();
	}
	line(r) {
		const u = (sel, list) => list.map((x) => `<option ${x === sel ? "selected" : ""}>${x}</option>`).join("");
		const typed = r.price_source === "Typed", pcs = r.qty_unit === "pcs";
		return `<div class="hkcc-row ${r.assumed ? "assumed" : ""}" data-item="${esc(r.item || "")}" data-ai="${r.ai_guess ? 1 : 0}" data-typed="${typed ? 1 : 0}">
			<div style="display:flex;gap:6px"><input class="hkcc-in" data-k="n" value="${esc(r.item_name || r.item || "")}" placeholder="${__("Ingredient")}" ${r.item ? "readonly" : ""}>
			<button class="btn btn-xs hkcc-del">×</button></div>
			<div class="hkcc-r2"><div><label>${__("Quantity")}</label><input class="hkcc-in" data-k="q" type="number" inputmode="decimal" value="${r.qty_g || ""}"></div>
			<div><label>&nbsp;</label><select class="hkcc-in" data-k="qu">${u(r.qty_unit || "g", ["g", "pcs"])}</select></div>
			<div><label>${__("Bulk price")}</label><input class="hkcc-in hkcc-p" data-k="bp" type="number" inputmode="decimal" value="${r.bulk_price || ""}"></div>
			<div><label>${__("Pack size")}</label><input class="hkcc-in hkcc-p" data-k="ps" type="number" inputmode="decimal" value="${r.pack_size || ""}"></div></div>
			<div class="hkcc-r2" style="grid-template-columns:1fr 1fr 1fr">
			<div><label>${__("Pack unit")}</label><select class="hkcc-in hkcc-p" data-k="pu">${u(r.pack_unit || "kg", ["g", "kg", "lb", "oz", "ml", "L", "pcs"])}</select></div>
			<div>${pcs ? `<label>${__("One piece (g)")}</label><input class="hkcc-in" data-k="pg" type="number" inputmode="decimal" value="${r.piece_g || ""}">` : `<input type="hidden" data-k="pg" value="0">`}</div>
			<div><label><input type="checkbox" data-k="as" ${r.assumed ? "checked" : ""}> ${__("Assumed price")}</label></div></div>
			<div class="hkcc-calc"><span>${typed ? __("Typed price") : r.item ? __("ERP buying price") : ""}${r.ai_guess ? ` <span class="hkcc-flag">${__("guess")}</span>` : ""}${r.price_note ? ` <span class="hkcc-flag">${__(r.price_note)}</span>` : ""}</span><span class="hkcc-live"></span></div></div>`;
	}
	live() {
		const UNITS = { g: 1, kg: 1000, lb: 453.592, oz: 28.3495, ml: 1, L: 1000, pcs: 0 };
		this.$b.find(".hkcc-row").each((i, el) => {
			const $e = $(el), x = (k) => $e.find(`[data-k="${k}"]`);
			const bp = Number(x("bp").val()) || 0, ps = Number(x("ps").val()) || 0, pu = x("pu").val(), q = Number(x("q").val()) || 0;
			const base = pu === "pcs" ? ps : ps * UNITS[pu];
			let t = "";
			if ((x("qu").val() === "pcs") !== (pu === "pcs")) t = __("Units differ (pcs vs weight)");
			else if (bp && base) { const c = bp / base; t = `${c.toFixed(4)}${pu === "pcs" ? "/pc" : "/g"} · ${cur(c * q)}`; }
			$e.find(".hkcc-live").text(t);
		});
	}
	cost_html() {
		const d = this.d;
		return `<div class="hkcc-card"><div class="hkcc-tot">${cur(d.total_cost)}</div>
			<div class="text-muted">${cur(d.cost_per_piece)} ${__("per piece")} · ${cur(d.cost_per_100g)} ${__("per 100 g")} · ${Math.round(d.recipe_weight_g || 0)} g ${__("recipe weight")}</div>
			<table class="hkcc-t" style="width:100%;margin-top:10px">${(d.ingredients || []).map((r) => `<tr><td>${esc(r.item_name || r.item)} ${r.qty_g} ${r.qty_unit === "pcs" ? "pcs" : "g"}
			${r.price_note ? `<span class="hkcc-flag">${__(r.price_note)}</span>` : ""}${r.assumed ? `<span class="hkcc-flag">${__("assumed price")}</span>` : ""}${r.ai_guess ? `<span class="hkcc-flag">${__("guess")}</span>` : ""}</td><td>${r.price_note ? "?" : cur(r.line_cost)}</td></tr>`).join("")}</table>
			${d.unpriced ? `<p class="text-muted" style="margin-top:8px">${__("Not counted (no price or pack size)")}: ${esc(d.unpriced)}</p>` : ""}
			<div class="hkcc-grid" style="grid-template-columns:1fr 1fr;margin-top:10px">
			<div><label>${__("Piece weight (g)")}</label><input class="hkcc-in" type="number" inputmode="decimal" data-f="piece_weight_g" value="${d.piece_weight_g || ""}"></div><div></div>
			<div><label>${__("Labour")}</label><input class="hkcc-in" type="number" data-f="labour_cost" value="${d.labour_cost || ""}"></div>
			<div><label>${__("Packaging")}</label><input class="hkcc-in" type="number" data-f="packaging_cost" value="${d.packaging_cost || ""}"></div></div>
			<textarea class="hkcc-in" data-f="notes" style="margin-top:10px" placeholder="${__("Notes")}">${esc(d.notes)}</textarea>
			<a class="btn btn-default hkcc-big" target="_blank" href="/api/method/frappe.utils.print_format.download_pdf?doctype=Cake%20Costing&name=${encodeURIComponent(d.name || "")}&format=Cake%20Costing%20Sheet&no_letterhead=1">${__("A4 sheet (PDF)")}</a>
			<a class="btn btn-link" href="/app/cake-costing/${encodeURIComponent(d.name || "")}"></a></div>`;
	}
	bind() {
		const $b = this.$b;
		$b.find(".hkcc-home").on("click", async () => { if (this.d.name || this.d.cake_name) await this.save(); this.home(); });
		$b.find(".hkcc-back").on("click", async () => { await this.save(STEPS[this.step - 1]); this.step--; this.draw(); });
		$b.find(".hkcc-next").on("click", async () => {
			if (this.step === 0 && !($b.find('[data-f="cake_name"]').val() || "").trim()) return frappe.show_alert({ message: __("Give the cake a name"), indicator: "orange" });
			if (this.step === 3) { await this.save("Cost"); return this.home(); }
			await this.save(STEPS[this.step + 1]); this.step++; this.draw();
		});
		$b.find(".hkcc-photo-btn").on("click", async () => {
			await this.save("Photo");
			new frappe.ui.FileUploader({ doctype: "Cake Costing", docname: this.d.name, folder: "Home", restrictions: { allowed_file_types: ["image/*"] }, make_attachments_public: 0,
				on_success: async (f) => { await frappe.xcall(API + "set_photo", { name: this.d.name, file_url: f.file_url }); this.d.photo = f.file_url; this.draw(); } });
		});
		$b.find(".hkcc-add").on("click", () => { this.collect(); this.d.ingredients.push({}); this.draw(); });
		$b.find(".hkcc-p").on("input change", (e) => $(e.currentTarget).closest(".hkcc-row").data("typed", 1));
		$b.find(".hkcc-row input, .hkcc-row select").on("input change", () => this.live());
		$b.find('.hkcc-row [data-k="qu"]').on("change", () => { this.collect(); this.draw(); });
		this.live();
		$b.find(".hkcc-del").on("click", (e) => { $(e.currentTarget).closest(".hkcc-row").remove(); this.collect(); });
		$b.find(".hkcc-guess").on("click", async () => {
			if (!this.d.photo) return frappe.show_alert({ message: __("Add a photo first"), indicator: "orange" });
			await this.save("Ingredients");
			const g = await frappe.xcall(API + "guess_from_photo", { name: this.d.name });
			this.collect(); this.d.ingredients = (this.d.ingredients || []).concat(g); this.draw();
		});
		$b.find('.hkcc-row [data-k="n"]:not([readonly])').each((i, el) => {
			$(el).on("change", async () => {
				const r = await frappe.db.get_list("Item", { filters: { disabled: 0, item_name: ["like", `%${$(el).val()}%`] }, fields: ["name", "item_name"], limit: 1 });
				if (r.length) { $(el).val(r[0].item_name).prop("readonly", true).closest(".hkcc-row").data("item", r[0].name); }
			});
		});
	}
}
})();
