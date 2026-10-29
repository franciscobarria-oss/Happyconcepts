// Copyright (c) 2026, Happy Kitchen and contributors
// Each kitchen screen keeps its helpers in its own scope, so several can load in one session.
(() => {
// Shared look for the kitchen screens (large touch targets; English or 繁體中文 via the EN / 中 toggle).
function hkk_css() {
	if (document.getElementById("hkk-css")) return;
	$(`<style id="hkk-css">
	.hkk { max-width: 1100px; margin: 0 auto; padding-bottom: 90px; }
	.hkk h4 { margin: 18px 0 10px; font-weight: 700; }
	.hkk-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 6px 0 12px; }
	.hkk-input, .hkk-select { min-height: 52px; font-size: 18px; padding: 8px 14px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--control-bg); }
	.hkk-input.hkk-num { width: 130px; text-align: right; font-size: 22px; }
	.hkk-search { flex: 1; min-width: 220px; }
	.hkk-chip { min-height: 44px; padding: 8px 16px; border-radius: 22px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 16px; }
	.hkk-chip.on { background: var(--primary); color: var(--hk-on-brand, #fff); border-color: var(--primary); }
	.hkk-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
	.hkk-tile { text-align: left; min-height: 96px; padding: 12px 14px; border-radius: 14px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 16px; line-height: 1.3; }
	.hkk-tile b { display: block; font-size: 17px; }
	.hkk-tile small { color: var(--text-muted); }
	.hkk-tile.sel { outline: 3px solid var(--primary); }
	.hkk-card { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px 16px; background: var(--card-bg); margin-bottom: 12px; }
	.hkk-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border-color); font-size: 17px; }
	.hkk-row:last-child { border-bottom: 0; }
	.hkk-step { display: inline-flex; align-items: center; gap: 6px; }
	.hkk-step button { width: 52px; height: 52px; border-radius: 12px; font-size: 26px; border: 1px solid var(--border-color); background: var(--card-bg); }
	.hkk-big { width: 100%; min-height: 62px; font-size: 20px; border-radius: 14px; margin-top: 14px; }
	.hkk-table { width: 100%; font-size: 16px; } .hkk-table td, .hkk-table th { padding: 10px 8px; border-bottom: 1px solid var(--border-color); }
	.hkk-table th { font-weight: 600; color: var(--text-muted); font-size: 13px; }
	.hkk-r { text-align: right; white-space: nowrap; }
	.hkk-bad { color: var(--hk-danger, var(--red-600, #c53030)); font-weight: 700; } .hkk-ok { color: var(--hk-success, var(--green-600, #2f855a)); }
	.hkk-flag { display: inline-block; background: var(--hk-warning-soft, var(--orange-100, #feebc8)); color: var(--hk-warning, var(--orange-800, #9c4221)); border-radius: 10px; padding: 2px 10px; margin: 2px 4px 2px 0; font-size: 14px; }
	.hkk-banner { padding: 14px 16px; border-radius: 12px; margin: 10px 0; font-size: 16px; background: var(--bg-light-gray); }
	.hkk-banner.ok { background: var(--hk-success-soft, var(--green-50, #f0fff4)); border: 1px solid var(--hk-success-soft, var(--green-300, #9ae6b4)); }
	.hkk-banner.warn { background: var(--hk-warning-soft, var(--orange-50, #fffaf0)); border: 1px solid var(--hk-warning-soft, var(--orange-300, #fbd38d)); }
	.hkk-cols { display: grid; grid-template-columns: 1.6fr 1fr; gap: 18px; align-items: start; }
	.hkk-sticky { position: sticky; top: calc(var(--navbar-height, 48px) + 10px); }
	@media (max-width: 900px) { .hkk-cols { grid-template-columns: 1fr; } .hkk-sticky { position: static; } }
	</style>`).appendTo("head");
}
const hkk_esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const hkk_num = (v, d = 2) => format_number(v || 0, null, d);
const hkk_cur = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"), 2);
// Receive Delivery: open PO -> confirm what arrived -> flags -> receive into stock.
const HKK_API = "happy_kitchen.recipe_management.kitchen.";

frappe.pages["receive-delivery"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Receive Delivery"), single_column: true });
	hkk_css();
	wrapper.hkk = new HKKReceive(wrapper);
};
frappe.pages["receive-delivery"].on_page_show = (wrapper) => wrapper.hkk.load(frappe.get_route()[1]);

class HKKReceive {
	constructor(wrapper) {
		this.$b = $(wrapper).find(".layout-main-section");
	}
	async load(po) {
		if (po) return this.open(po);
		const pos = await frappe.xcall(HKK_API + "open_purchase_orders");
		this.$b.html(`<div class="hkk">
			<div class="hkk-bar"><input class="hkk-input hkk-search" type="search" placeholder="${__("Find supplier or PO")}"></div>
			<div class="hkk-tiles hkk-pos"></div></div>`);
		const draw = (q) => {
			q = (q || "").toLowerCase();
			const list = pos.filter((p) => !q || `${p.name} ${p.supplier_name}`.toLowerCase().includes(q));
			this.$b.find(".hkk-pos").html(list.map((p) => `<button class="hkk-tile" data-po="${hkk_esc(p.name)}"><b>${hkk_esc(p.supplier_name)}</b>
				<small>${hkk_esc(p.name)} · ${__("due")} ${frappe.datetime.str_to_user(p.schedule_date)}<br>${format_currency(p.grand_total, p.currency)} · ${hkk_num(p.per_received, 0)}% ${__("received")}</small></button>`).join("")
				|| `<p class="text-muted">${__("No purchase orders waiting for delivery.")}</p>`);
			this.$b.find(".hkk-pos .hkk-tile").on("click", (e) => frappe.set_route("receive-delivery", $(e.currentTarget).data("po")));
		};
		this.$b.find(".hkk-search").on("input", (e) => draw(e.target.value));
		draw("");
	}
	async open(po) {
		this.po = await frappe.xcall(HKK_API + "purchase_order_lines", { po });
		const d = this.po;
		this.$b.html(`<div class="hkk">
			<div class="hkk-card"><h4 style="margin-top:0">${hkk_esc(d.supplier_name)} <small class="text-muted">${hkk_esc(d.name)}</small></h4>
				<div class="hkk-bar">
					<input class="hkk-input hkk-dn" style="flex:1;min-width:220px" placeholder="${__("Supplier delivery note / invoice no.")}">
					<button class="btn btn-default hkk-all">${__("All arrived as ordered")}</button>
				</div></div>
			<div class="hkk-card"><table class="hkk-table">
				<tr><th>${__("Item")}</th><th class="hkk-r">${__("Ordered")}</th><th class="hkk-r">${__("Received")}</th><th class="hkk-r">${__("Invoice price")}<br><small class="text-muted">${__("only if different")}</small></th><th>${__("Check")}</th></tr>
				${d.lines.map((l) => `<tr data-l="${hkk_esc(l.po_detail)}"><td><b>${hkk_esc(l.item_name)}</b><br><small class="text-muted">${hkk_esc(l.item)}${l.supplier_sku ? " · " + __("Supplier SKU") + " " + hkk_esc(l.supplier_sku) : ""}</small></td>
					<td class="hkk-r">${hkk_num(l.pending_qty)} ${hkk_esc(l.uom)}<br><small class="text-muted">@ ${format_currency(l.rate, d.currency, 4)}</small></td>
					<td class="hkk-r"><input class="hkk-input hkk-num hkk-qty" type="number" inputmode="decimal" step="any" min="0" value="${l.pending_qty}"></td>
					<td class="hkk-r"><input class="hkk-input hkk-num hkk-rate" type="number" inputmode="decimal" step="any" min="0" placeholder="${__("same")}"></td>
					<td class="hkk-flags"></td></tr>`).join("")}
			</table></div>
			<input class="hkk-input hkk-notes" style="width:100%" placeholder="${__("Notes, e.g. damaged box")}">
			<div class="hkk-summary"></div>
			<button class="btn btn-primary hkk-big hkk-receive">${__("Receive into stock")}</button>
			<button class="btn btn-default hkk-big hkk-back">${__("Back to orders")}</button>
		</div>`);
		this.$b.find(".hkk-qty, .hkk-rate").on("input", () => this.check());
		this.$b.find(".hkk-all").on("click", () => { this.$b.find("tr[data-l]").each((_, tr) => {
			const l = d.lines.find((x) => x.po_detail === $(tr).data("l")); $(tr).find(".hkk-qty").val(l.pending_qty); $(tr).find(".hkk-rate").val(""); }); this.check(); });
		this.$b.find(".hkk-receive").on("click", () => this.receive());
		this.$b.find(".hkk-back").on("click", () => frappe.set_route("receive-delivery"));
		this.check();
	}
	lines() {
		return this.$b.find("tr[data-l]").toArray().map((tr) => {
			const l = this.po.lines.find((x) => x.po_detail === $(tr).data("l"));
			return { po_detail: l.po_detail, item: l.item, ordered_qty: l.pending_qty, po_rate: l.rate,
				received_qty: Number($(tr).find(".hkk-qty").val()) || 0, invoice_rate: Number($(tr).find(".hkk-rate").val()) || 0 };
		});
	}
	async check() {
		clearTimeout(this.t);
		this.t = setTimeout(async () => {
			const lines = this.lines();
			const s = await frappe.xcall(HKK_API + "check_delivery", { lines });
			this.$b.find("tr[data-l]").each((k, tr) => $(tr).find(".hkk-flags").html(
				s.lines[k].flags.length ? s.lines[k].flags.map((f) => `<span class="hkk-flag">${hkk_esc(f)}</span>`).join("") : `<span class="hkk-ok">✓</span>`));
			this.$b.find(".hkk-summary").html(s.has_discrepancy
				? `<div class="hkk-banner warn">${__("{0} line(s) differ from the order. Stock is received at the ordered price; the differences are flagged on the receipt for the office.", [s.flagged_lines])}</div>`
				: `<div class="hkk-banner ok">${__("Everything matches the order.")}</div>`);
		}, 250);
	}
	receive() {
		const lines = this.lines();
		if (!lines.some((l) => l.received_qty > 0)) return frappe.msgprint(__("Enter what arrived for at least one line."));
		frappe.confirm(__("Receive these goods into stock?"), async () => {
			const r = await frappe.xcall(HKK_API + "receive_po", { po: this.po.name, lines,
				supplier_delivery_note: this.$b.find(".hkk-dn").val(), notes: this.$b.find(".hkk-notes").val() });
			frappe.msgprint({
				title: __("Goods received"),
				indicator: r.has_discrepancy ? "orange" : "green",
				message: `<a href="/app/purchase-receipt/${r.name}">${r.name}</a> · ${hkk_cur(r.grand_total)}${r.flags ? `<br><br><b>${__("Flagged")}:</b><br>${hkk_esc(r.flags).replace(/\n/g, "<br>")}` : ""}`,
			});
			frappe.set_route("receive-delivery");
		});
	}
}
})();
