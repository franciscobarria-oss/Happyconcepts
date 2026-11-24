// Copyright (c) 2026, Happy Kitchen and contributors
// Read a photo of a handwritten recipe (English / Chinese): Claude first, Gemini as backup, then a Draft Recipe.
(() => {
const API = "happy_kitchen.recipe_management.photo_reader.";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const UOMS = ["", "g", "kg", "oz", "lb", "ml", "l", "piece"];

function css() {
	if (document.getElementById("hkrp-css")) return;
	$(`<style id="hkrp-css">
	.hkrp { max-width: 640px; margin: 0 auto; padding-bottom: 80px; }
	.hkrp-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px; background: var(--card-bg); margin-bottom: 12px; }
	.hkrp-in { min-height: 46px; font-size: 16px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border-color); background: var(--control-bg); width: 100%; }
	.hkrp-row { display: grid; grid-template-columns: 1fr 76px 74px 34px; gap: 6px; align-items: start; margin-bottom: 10px; }
	.hkrp-big { width: 100%; min-height: 54px; font-size: 18px; border-radius: 12px; margin-top: 8px; }
	.hkrp-photo { width: 100%; max-height: 260px; object-fit: contain; border-radius: 10px; margin-bottom: 10px; }
	.hkrp-flag { background: var(--hk-warning-soft, #feebc8); border-radius: 8px; padding: 2px 8px; font-size: 12px; }
	</style>`).appendTo("head");
}

frappe.pages["recipe-photo"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Read recipe photo"), single_column: true });
	css();
	wrapper.hkrp = new RecipePhoto(wrapper);
};
frappe.pages["recipe-photo"].on_page_show = (wrapper) => wrapper.hkrp.start();

class RecipePhoto {
	constructor(wrapper) { this.$b = $(wrapper).find(".layout-main-section"); this.r = null; this.file = null; }
	async start() {
		this.r = null; this.file = null;
		const st = await frappe.xcall(API + "status");
		const none = !st.claude && !st.gemini;
		this.$b.html(`<div class="hkrp"><div class="hkrp-card">
			<p>${__("Take a photo of a handwritten recipe (English or Chinese). The system reads it into text and a draft recipe you can check.")}</p>
			<p class="text-muted">${__("Tip: flat page, good light, whole page in the picture.")}</p>
			${none ? `<p><span class="hkrp-flag">${__("No reader is set up: add a Claude key in Recipe Settings or a Gemini key in Gmail Settings.")}</span></p>` : ""}
			<button class="btn btn-primary hkrp-big hkrp-take" ${none ? "disabled" : ""}>${__("Take or upload photo")}</button>
			<button class="btn btn-default hkrp-big hkrp-test" ${none ? "disabled" : ""}>${__("Test the reader")}</button><p class="hkrp-test-out text-muted" style="margin-top:8px"></p></div></div>`);
		this.$b.find(".hkrp-test").on("click", async (e) => {
			const $o = this.$b.find(".hkrp-test-out").text(__("Testing...")); $(e.currentTarget).prop("disabled", true);
			try {
				const t = await frappe.xcall(API + "self_test");
				$o.text(__("Works: read by {0}, {1} ingredients ({2})", [t.engine, t.ingredients, t.names.join(", ")]) + (t.problems.length ? " | " + t.problems.join("; ") : ""));
			} catch (err) { $o.text(__("The test failed: check the keys in Gmail Settings and Recipe Settings.")); }
			$(e.currentTarget).prop("disabled", false);
		});
		this.$b.find(".hkrp-take").on("click", () => this.pick());
	}
	pick() {
		new frappe.ui.FileUploader({
			folder: "Home", make_attachments_public: 0, allow_multiple: false,
			restrictions: { allowed_file_types: ["image/*"] }, allow_take_photo: true,
			on_success: (f) => { this.file = f.file_url; this.read(); },
		});
	}
	async read() {
		this.$b.html(`<div class="hkrp"><div class="hkrp-card"><img class="hkrp-photo" src="${esc(this.file)}"><p>${__("Reading the recipe...")}</p></div></div>`);
		try {
			this.r = await frappe.xcall(API + "read_photo", { file_url: this.file });
		} catch (e) {
			this.$b.html(`<div class="hkrp"><div class="hkrp-card"><img class="hkrp-photo" src="${esc(this.file)}">
				<p>${__("The photo could not be read. Try a sharper, well-lit photo, or type the recipe by hand.")}</p>
				<button class="btn btn-primary hkrp-big hkrp-again">${__("Try another photo")}</button></div></div>`);
			this.$b.find(".hkrp-again").on("click", () => this.start());
			return;
		}
		this.draw();
	}
	row(i) {
		const g = this.r.ingredients[i];
		return `<div class="hkrp-row" data-i="${i}"><div><input class="hkrp-in n" value="${esc(g.name)}">
			<div class="hkrp-item" style="margin-top:4px"></div>${g.note ? `<small class="text-muted">${esc(g.note)}</small>` : ""}</div>
			<input class="hkrp-in q" type="number" inputmode="decimal" step="any" value="${g.qty || ""}">
			<select class="hkrp-in u">${UOMS.map((u) => `<option ${u === g.uom ? "selected" : ""}>${u}</option>`).join("")}</select>
			<button class="btn btn-xs hkrp-del">×</button></div>`;
	}
	draw() {
		const r = this.r;
		this.$b.html(`<div class="hkrp">
			<div class="hkrp-card"><img class="hkrp-photo" src="${esc(this.file)}">
			<span class="hkrp-flag">${__("Read by {0}", [esc(r.engine)])}</span>
			${r.unclear.length ? `<p style="margin-top:8px"><b>${__("Hard to read")}:</b> ${r.unclear.map(esc).join("; ")}</p>` : ""}
			<h6 style="margin-top:12px">${__("Text")}</h6><textarea class="hkrp-in hkrp-text" rows="8">${esc(r.text)}</textarea></div>
			<div class="hkrp-card"><h6>${__("Ingredients")}</h6>${r.ingredients.map((_, i) => this.row(i)).join("") || `<p class="text-muted">${__("No ingredients found")}</p>`}
			<h6 style="margin-top:12px">${__("Method")}</h6><textarea class="hkrp-in hkrp-steps" rows="6">${esc(r.steps.join("\n"))}</textarea></div>
			<div class="hkrp-card"><h6>${__("Make a draft recipe for item")}</h6><div class="hkrp-target"></div>
			<p class="text-muted" style="margin-top:6px">${__("Lines with no matching item, quantity or unit are kept in the recipe notes.")}</p>
			<button class="btn btn-primary hkrp-big hkrp-create">${__("Create draft recipe")}</button>
			<button class="btn btn-default hkrp-big hkrp-again">${__("Another photo")}</button></div></div>`);
		const link = (parent, value, ph) => {
			const c = frappe.ui.form.make_control({ parent, df: { fieldtype: "Link", options: "Item", fieldname: "item", placeholder: ph, only_select: false }, render_input: true });
			if (value) c.set_value(value);
			return c;
		};
		this.ctl = this.r.ingredients.map((g, i) => link(this.$b.find(`.hkrp-row[data-i=${i}] .hkrp-item`), g.item, __("Item")));
		this.target = link(this.$b.find(".hkrp-target"), null, __("Item the recipe is for"));
		this.$b.find(".hkrp-again").on("click", () => this.start());
		this.$b.find(".hkrp-del").on("click", (e) => { this.collect(); this.r.ingredients.splice($(e.currentTarget).closest(".hkrp-row").data("i"), 1); this.draw(); });
		this.$b.find(".hkrp-create").on("click", () => this.create());
	}
	collect() {
		this.r.ingredients = this.r.ingredients.map((g, i) => {
			const $r = this.$b.find(`.hkrp-row[data-i=${i}]`);
			return { ...g, name: $r.find(".n").val(), qty: Number($r.find(".q").val()) || 0, uom: $r.find(".u").val(), item: this.ctl[i].get_value() || null };
		});
		this.r.text = this.$b.find(".hkrp-text").val();
		this.r.steps = (this.$b.find(".hkrp-steps").val() || "").split("\n").map((s) => s.trim()).filter(Boolean);
	}
	async create() {
		this.collect();
		const item = this.target.get_value();
		if (!item) return frappe.show_alert({ message: __("Pick the item this recipe is for"), indicator: "orange" });
		const res = await frappe.xcall(API + "create_draft", { item, data: this.r, file_url: this.file });
		frappe.show_alert({ message: __("Draft recipe made: {0} lines added, {1} left in the notes", [res.added, res.left_out]), indicator: "green" }, 6);
		frappe.set_route("Form", "Recipe", res.name);
	}
}
})();
