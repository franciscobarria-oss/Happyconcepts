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
	.hkcc { max-width: 560px; margin: 0 auto; padding-bottom: 80px; }
	.hkcc-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px; background: var(--card-bg); margin-bottom: 12px; }
	.hkcc-in { min-height: 48px; font-size: 17px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border-color); background: var(--control-bg); width: 100%; }
	.hkcc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
	.hkcc-grid label { font-size: 12px; color: var(--text-muted); }
	.hkcc-steps { display: flex; gap: 6px; margin-bottom: 12px; } .hkcc-steps i { flex: 1; height: 5px; border-radius: 3px; background: var(--border-color); } .hkcc-steps i.on { background: var(--primary); }
	.hkcc-photo { width: 100%; max-height: 300px; object-fit: cover; border-radius: 10px; margin-bottom: 10px; }
	.hkcc-row { display: grid; grid-template-columns: 1fr 86px 34px; gap: 8px; align-items: center; margin-bottom: 8px; }
	.hkcc-big { width: 100%; min-height: 54px; font-size: 18px; border-radius: 12px; margin-top: 8px; }
	.hkcc-tot { font-size: 34px; font-weight: 700; }
	.hkcc-flag { background: var(--hk-warning-soft, #feebc8); border-radius: 8px; padding: 2px 8px; font-size: 12px; margin-left: 4px; }
	.hkcc-t td { padding: 6px 0; border-bottom: 1px solid var(--border-color); } .hkcc-t td:last-child { text-align: right; }
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
		["cake_name", "shape", "height_cm", "width_cm", "length_cm", "weight_g", "slices", "labour_cost", "packaging_cost", "notes"].forEach((f) => {
			if (v(f).length) this.d[f] = v(f).val();
		});
		if ($b.find(".hkcc-row").length) {
			this.d.ingredients = $b.find(".hkcc-row").map((i, el) => ({
				item: $(el).data("item") || null, item_name: $(el).find(".n").val(), qty_g: Number($(el).find(".g").val()) || 0, ai_guess: $(el).data("ai") ? 1 : 0,
			})).get().filter((r) => r.item_name || r.item);
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
		return `<div class="hkcc-row" data-item="${esc(r.item || "")}" data-ai="${r.ai_guess ? 1 : 0}"><div><input class="hkcc-in n" value="${esc(r.item_name || r.item || "")}" placeholder="${__("Ingredient")}" ${r.item ? "readonly" : ""}>
			${r.item ? "" : `<small class="text-muted">${__("Pick an item")}</small>`}</div>
			<input class="hkcc-in g" type="number" inputmode="decimal" value="${r.qty_g || ""}" placeholder="g"><button class="btn btn-xs hkcc-del">×</button></div>`;
	}
	cost_html() {
		const d = this.d;
		return `<div class="hkcc-card"><div class="hkcc-tot">${cur(d.total_cost)}</div>
			<div class="text-muted">${cur(d.cost_per_slice)} ${__("per slice")} · ${cur(d.cost_per_100g)} ${__("per 100 g")}</div>
			<table class="hkcc-t" style="width:100%;margin-top:10px">${(d.ingredients || []).map((r) => `<tr><td>${esc(r.item_name || r.item)} ${r.qty_g} g
			${r.price_note ? `<span class="hkcc-flag">${__(r.price_note)}</span>` : ""}${r.ai_guess ? `<span class="hkcc-flag">${__("guess")}</span>` : ""}</td><td>${r.price_note ? "?" : cur(r.line_cost)}</td></tr>`).join("")}</table>
			${d.unpriced ? `<p class="text-muted" style="margin-top:8px">${__("Not counted (no price or pack size)")}: ${esc(d.unpriced)}</p>` : ""}
			<div class="hkcc-grid" style="grid-template-columns:1fr 1fr;margin-top:10px">
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
		$b.find(".hkcc-del").on("click", (e) => { $(e.currentTarget).closest(".hkcc-row").remove(); this.collect(); });
		$b.find(".hkcc-guess").on("click", async () => {
			if (!this.d.photo) return frappe.show_alert({ message: __("Add a photo first"), indicator: "orange" });
			await this.save("Ingredients");
			const g = await frappe.xcall(API + "guess_from_photo", { name: this.d.name });
			this.collect(); this.d.ingredients = (this.d.ingredients || []).concat(g); this.draw();
		});
		$b.find(".hkcc-row .n:not([readonly])").each((i, el) => {
			$(el).on("change", async () => {
				const r = await frappe.db.get_list("Item", { filters: { disabled: 0, item_name: ["like", `%${$(el).val()}%`] }, fields: ["name", "item_name"], limit: 1 });
				if (r.length) { $(el).val(r[0].item_name).prop("readonly", true).closest(".hkcc-row").data("item", r[0].name); }
			});
		});
	}
}
})();
