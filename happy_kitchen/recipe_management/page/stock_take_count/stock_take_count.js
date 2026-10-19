// Copyright (c) 2026, Happy Kitchen and contributors
// For license information, please see license.txt

// Count screen for iPad: one ingredient per row, grouped by storage area, big
// touch targets and the decimal keypad. Every entry is written to localStorage
// first, then sent to the server; anything that fails stays queued and is
// retried, so a dropped connection mid-count loses nothing.

const HK_STK_API = "happy_kitchen.recipe_management.doctype.stock_take.stock_take.";

frappe.pages["stock-take-count"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Stock Take Count"), single_column: true });
	wrapper.hk_count = new HKStockTakeCount(wrapper);
};

frappe.pages["stock-take-count"].on_page_show = function (wrapper) {
	wrapper.hk_count.load(frappe.get_route()[1]);
};

// Pack counts as a list, one per pack size; screens before hk14 queued a single number.
function hk_stk_packs(v) {
	if (v === null || v === undefined) return [];
	return Array.isArray(v) ? v : [v];
}

class HKStockTakeCount {
	constructor(wrapper) {
		this.page = wrapper.page;
		this.$body = $(wrapper).find(".layout-main-section");
		this.inject_css();
		this.retry_timer = null;
		window.addEventListener("online", () => this.flush());
		document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && this.flush());
	}

	key() {
		return `hk-stock-take-${this.name}`;
	}
	pending() {
		try {
			return JSON.parse(localStorage.getItem(this.key()) || "{}");
		} catch (e) {
			return {};
		}
	}
	set_pending(p) {
		try {
			localStorage.setItem(this.key(), JSON.stringify(p));
		} catch (e) {
			/* storage blocked: entries still go straight to the server */
		}
	}

	async load(name) {
		if (!name) return this.render_picker();
		this.name = name;
		this.$body.html(`<div class="hk-stk-loading">${__("Loading count sheet...")}</div>`);
		try {
			this.data = await frappe.xcall(HK_STK_API + "get_count_sheet", { name });
		} catch (e) {
			const local = Object.keys(this.pending()).length;
			this.$body.html(`<div class="hk-stk-banner hk-red">${__("Can't reach the server.")} ${
				local ? __("{0} entries are saved on this iPad and will be sent when you're back online.", [local]) : ""
			} <button class="btn btn-default hk-stk-retry">${__("Try again")}</button></div>`);
			this.$body.find(".hk-stk-retry").on("click", () => this.load(name));
			return;
		}
		this.page.set_title(`${__("Stock Take")} ${name}`);
		this.page.clear_menu();
		this.page.add_menu_item(__("Print Count Sheet"), () =>
			window.open(`/api/method/happy_kitchen.recipe_management.count_print.sheet?take=${encodeURIComponent(name)}`)
		);
		this.render();
		this.flush();
	}

	async render_picker() {
		this.page.set_title(__("Stock Take Count"));
		const [open, sheets] = await Promise.all([
			frappe.db.get_list("Stock Take", { filters: { docstatus: 0 }, fields: ["name", "posting_date", "status", "counted_rows", "total_rows", "stock_take_sheet"], order_by: "posting_date desc", limit: 20 }),
			frappe.db.get_list("Stock Take Sheet", { fields: ["name", "active_rows"], limit: 50 }),
		]);
		const card = (t) => `<button class="hk-stk-pick" data-name="${t.name}"><b>${t.name}</b> · ${frappe.datetime.str_to_user(t.posting_date)}
			<span class="text-muted">${frappe.utils.escape_html(t.stock_take_sheet)} · ${t.counted_rows || 0}/${t.total_rows || 0} · ${__(t.status)}</span></button>`;
		const sheet = (s) => `<button class="hk-stk-new" data-sheet="${frappe.utils.escape_html(s.name)}">+ ${__("New count")}: <b>${frappe.utils.escape_html(s.name)}</b>
			<span class="text-muted">${s.active_rows || 0} ${__("ingredients")}</span></button>`;
		this.$body.html(`<div class="hk-stk">
			<h4>${__("Continue a count")}</h4>${open.map(card).join("") || `<p class="text-muted">${__("No open counts.")}</p>`}
			<h4>${__("Start a new count")}</h4>${sheets.map(sheet).join("") || `<p class="text-muted">${__("Create a Stock Take Sheet first.")}</p>`}
		</div>`);
		this.$body.find(".hk-stk-pick").on("click", (e) => frappe.set_route("stock-take-count", $(e.currentTarget).data("name")));
		this.$body.find(".hk-stk-new").on("click", async (e) => {
			const name = await frappe.xcall(HK_STK_API + "make_stock_take", { sheet: $(e.currentTarget).data("sheet") });
			frappe.set_route("stock-take-count", name);
		});
	}

	render() {
		const d = this.data;
		const esc = frappe.utils.escape_html;
		const pending = this.pending();
		const groups = [];
		d.rows.forEach((r) => {
			let g = groups.find((x) => x.area === r.storage_area);
			if (!g) groups.push((g = { area: r.storage_area, rows: [] }));
			g.rows.push(r);
		});
		// "Pack (22.7 kg)" / "Case (360 pcs)": the pack size in words, not a raw factor
		const pack_size = (r, factor) => {
			const f = Number(factor) || 0;
			if (r.stock_uom === "Gram") return f >= 1000 ? `${format_number(f / 1000, null, f % 1000 ? 2 : 0)} kg` : `${format_number(f, null, 0)} g`;
			return `${format_number(f, null, 0)} ${r.stock_uom === "Nos" ? "pcs" : esc(r.stock_uom || "")}`;
		};
		const row_html = (r) => {
			const local = pending[r.row];
			// boxes: "qty" (loose units) and "p0".."p2" (one per pack size)
			const val = (k) => {
				let v = null;
				if (k === "qty") v = local !== undefined ? local.qty : r.counted ? r.counted_qty : null;
				else v = hk_stk_packs(local !== undefined ? local.packs : r.counted ? r.counted_packs : null)[Number(k.slice(1))];
				return v === null || v === undefined ? "" : v;
			};
			const input = (kind, unit, label) => `<span class="hk-stk-pair"><input class="hk-stk-input" data-kind="${kind}" type="number"
				inputmode="decimal" step="any" min="0" enterkeyhint="next" value="${val(kind)}" ${d.editable ? "" : "disabled"}
				aria-label="${esc(r.item_name)} ${esc(label)}"><span class="hk-stk-unit">${unit}</span></span>`;
			const packs = r.packs || [];
			const inputs = packs
				.map((p, i) => input(`p${i}`, `${esc(p.uom)}<small>${pack_size(r, p.factor)}</small>`, p.uom))
				.concat(input("qty", esc(r.count_uom), r.count_uom))
				.join(`<span class="hk-stk-plus">+</span>`);
			return `<div class="hk-stk-row${packs.length > 1 ? " hk-stk-multi" : ""}" data-row="${r.row}">
				<div class="hk-stk-name">${esc(r.item_name || r.item)}<small>${esc(r.item)}</small></div>
				<div class="hk-stk-inputs">${inputs}</div>
				<div class="hk-stk-state">${local !== undefined ? "…" : r.counted ? "✓" : ""}</div>
			</div>`;
		};
		this.$body.html(`<div class="hk-stk">
			${d.rejection_comment ? `<div class="hk-stk-banner hk-red"><b>${__("Sent back")}:</b> ${esc(d.rejection_comment)}</div>` : ""}
			${!d.editable ? `<div class="hk-stk-banner">${__("This count is {0} and can't be changed.", [__(d.status)])}</div>` : ""}
			<div class="hk-stk-bar">
				<span class="hk-stk-progress"></span>
				<span class="hk-stk-sync"></span>
			</div>
			<input class="hk-stk-search" type="search" placeholder="${__("Find ingredient")}">
			${groups.map((g) => `<div class="hk-stk-group"><div class="hk-stk-area">${esc((g.area || "").replace(/ - [^-]+$/, ""))}
				<span>${g.rows.length}</span></div>${g.rows.map(row_html).join("")}</div>`).join("")}
			${d.editable ? `<button class="btn btn-primary hk-stk-submit">${__("Submit for Approval")}</button>` : ""}
		</div>`);

		const $inputs = this.$body.find(".hk-stk-input");
		$inputs.on("input", (e) => this.queue(e.currentTarget, 700));
		$inputs.on("change blur", (e) => this.queue(e.currentTarget, 0));
		$inputs.on("keydown", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				const i = $inputs.index(e.currentTarget);
				const next = $inputs.get(i + 1);
				next ? next.focus() : e.currentTarget.blur();
			}
		});
		this.$body.find(".hk-stk-search").on("input", (e) => {
			const q = e.currentTarget.value.trim().toLowerCase();
			this.$body.find(".hk-stk-row").each((_, el) => $(el).toggle(!q || el.textContent.toLowerCase().includes(q)));
		});
		this.$body.find(".hk-stk-submit").on("click", () => this.submit());
		this.update_bar();
	}

	queue(input, delay) {
		const $row = $(input).closest(".hk-stk-row");
		const row = $row.data("row");
		const read = (kind) => {
			const el = $row.find(`.hk-stk-input[data-kind="${kind}"]`).get(0);
			if (!el) return { v: null, ok: true };
			const raw = el.value.trim();
			const v = raw === "" ? null : Number(raw);
			const ok = v === null || (!isNaN(v) && v >= 0);
			$(el).toggleClass("hk-bad", !ok);
			return { v, ok };
		};
		const r = this.data.rows.find((x) => x.row === row);
		const n_packs = r ? (r.packs || []).length : 0;
		const q = read("qty");
		const k = Array.from({ length: n_packs }, (_, i) => read(`p${i}`));
		if (!q.ok || k.some((x) => !x.ok)) return;
		// a row with any box filled counts as counted; the empty boxes mean 0
		const empty = q.v === null && k.every((x) => x.v === null);
		const qty = empty ? null : q.v || 0;
		const packs = n_packs && !empty ? k.map((x) => x.v || 0) : null;
		const p = this.pending();
		const was = hk_stk_packs(r && r.counted_packs);
		const unchanged = r && ((empty && !r.counted) ||
			(r.counted && !empty && Number(r.counted_qty || 0) === qty && (packs || []).every((v, i) => Number(was[i] || 0) === v)));
		if (unchanged && !p[row]) return;
		p[row] = { qty, packs, ts: Date.now() };
		this.set_pending(p);
		this.mark(row, "…");
		this.update_bar();
		clearTimeout(this.flush_timer);
		this.flush_timer = setTimeout(() => this.flush(), delay);
	}

	async flush() {
		if (!this.name || this.flushing) return;
		const p = this.pending();
		const rows = Object.keys(p);
		if (!rows.length) return this.update_bar();
		this.flushing = true;
		const sent = rows.map((row) => ({ row, qty: p[row].qty, packs: p[row].packs ?? null, ts: p[row].ts }));
		try {
			const r = await frappe.xcall(HK_STK_API + "save_counts", { name: this.name, counts: sent.map(({ row, qty, packs }) => ({ row, qty, packs })) });
			const now = this.pending();
			sent.forEach((s) => {
				const row = this.data.rows.find((x) => x.row === s.row);
				if (row && (r.saved || []).includes(s.row)) {
					row.counted = s.qty === null && s.packs === null ? 0 : 1;
					row.counted_qty = s.qty;
					row.counted_packs = hk_stk_packs(s.packs);
				}
				// only clear entries that weren't edited again while saving
				if (now[s.row] && now[s.row].ts === s.ts) delete now[s.row];
				this.mark(s.row, now[s.row] ? "…" : s.qty === null && s.packs === null ? "" : "✓");
			});
			this.set_pending(now);
			this.offline = false;
		} catch (e) {
			this.offline = true;
			clearTimeout(this.retry_timer);
			this.retry_timer = setTimeout(() => this.flush(), 5000);
		} finally {
			this.flushing = false;
			this.update_bar();
			if (!this.offline && Object.keys(this.pending()).length) setTimeout(() => this.flush(), 300);
		}
	}

	mark(row, symbol) {
		this.$body.find(`.hk-stk-row[data-row="${row}"] .hk-stk-state`).text(symbol);
	}

	update_bar() {
		if (!this.data) return;
		const p = this.pending();
		const counted = this.data.rows.filter((r) => (p[r.row] ? p[r.row].qty !== null || p[r.row].packs != null : r.counted)).length;
		const waiting = Object.keys(p).length;
		this.$body.find(".hk-stk-progress").text(__("{0} of {1} counted", [counted, this.data.rows.length]));
		const $sync = this.$body.find(".hk-stk-sync");
		if (this.offline) $sync.attr("class", "hk-stk-sync hk-red").text(__("Offline: {0} saved on this iPad, retrying", [waiting]));
		else if (waiting) $sync.attr("class", "hk-stk-sync hk-orange").text(__("Saving {0}…", [waiting]));
		else $sync.attr("class", "hk-stk-sync hk-green").text(__("All saved"));
	}

	async submit() {
		await this.flush();
		if (Object.keys(this.pending()).length) return frappe.msgprint(__("Some counts aren't saved yet. Check the connection and try again."));
		const missing = this.data.rows.filter((r) => !r.counted).length;
		if (missing) return frappe.msgprint(__("{0} ingredients have no count yet. Enter 0 if there is none.", [missing]));
		frappe.confirm(__("Submit this count for approval? It can't be changed while it waits."), async () => {
			await frappe.xcall(HK_STK_API + "submit_for_approval", { name: this.name });
			frappe.show_alert({ message: __("Submitted for approval"), indicator: "green" });
			this.load(this.name);
		});
	}

	inject_css() {
		if (document.getElementById("hk-stk-css")) return;
		const css = `
		.hk-stk { max-width: 860px; margin: 0 auto; padding-bottom: 80px; }
		.hk-stk h4 { margin: 24px 0 8px; }
		.hk-stk-loading { padding: 40px; text-align: center; font-size: 18px; }
		.hk-stk-banner { padding: 14px 16px; border-radius: 10px; margin: 8px 0; background: var(--bg-light-gray); font-size: 16px; }
		.hk-stk-banner.hk-red { background: var(--bg-red); color: var(--text-on-red); }
		.hk-stk-bar { position: sticky; top: var(--navbar-height, 48px); z-index: 3; display: flex; justify-content: space-between;
			gap: 8px; padding: 12px 4px; background: var(--bg-color); font-size: 16px; font-weight: 600; }
		.hk-stk-sync.hk-green { color: var(--text-on-green, green); } .hk-stk-sync.hk-orange { color: var(--text-on-orange, #c26e00); }
		.hk-stk-sync.hk-red { color: var(--text-on-red, #c00); }
		.hk-stk-search { width: 100%; min-height: 48px; font-size: 18px; padding: 8px 14px; border-radius: 10px;
			border: 1px solid var(--border-color); margin-bottom: 8px; }
		.hk-stk-area { position: sticky; top: calc(var(--navbar-height, 48px) + 46px); z-index: 2; background: var(--bg-color);
			padding: 14px 4px 6px; font-size: 20px; font-weight: 700; display: flex; justify-content: space-between; }
		.hk-stk-area span { font-weight: 400; color: var(--text-muted); font-size: 15px; }
		.hk-stk-row { display: grid; grid-template-columns: 1fr auto 32px; align-items: center; gap: 10px;
			min-height: 68px; padding: 8px 6px; border-bottom: 1px solid var(--border-color); }
		.hk-stk-name { font-size: 18px; line-height: 1.25; overflow-wrap: anywhere; }
		.hk-stk-name small { display: block; color: var(--text-muted); font-size: 13px; }
		.hk-stk-input { width: 150px; min-height: 52px; font-size: 22px; text-align: right; padding: 6px 12px;
			border-radius: 10px; border: 2px solid var(--border-color); }
		.hk-stk-input:focus { border-color: var(--primary); outline: none; }
		.hk-stk-input.hk-bad { border-color: var(--hk-danger, var(--red-500, #e53e3e)); }
		.hk-stk-unit { font-size: 16px; color: var(--text-muted); min-width: 44px; display: inline-block; }
		.hk-stk-unit small { display: block; font-size: 11px; }
		.hk-stk-inputs { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
		.hk-stk-pair { display: inline-flex; align-items: center; gap: 6px; }
		.hk-stk-plus { font-size: 20px; color: var(--text-muted); }
		.hk-stk-state { font-size: 22px; color: var(--hk-success, var(--green-600, green)); text-align: center; }
		.hk-stk-submit { width: 100%; min-height: 60px; font-size: 20px; margin-top: 24px; border-radius: 12px; }
		.hk-stk-pick, .hk-stk-new { display: block; width: 100%; text-align: left; min-height: 64px; padding: 12px 16px; margin: 8px 0;
			border-radius: 12px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 18px; }
		.hk-stk-pick span, .hk-stk-new span { display: block; font-size: 14px; }
		/* several pack sizes: the boxes go on their own line under the name */
		.hk-stk-row.hk-stk-multi { grid-template-columns: 1fr 32px; }
		.hk-stk-multi .hk-stk-inputs { grid-column: 1; grid-row: 2; justify-content: flex-start; }
		.hk-stk-multi .hk-stk-state { grid-column: 2; grid-row: 1 / span 2; }
		.hk-stk-multi .hk-stk-input { width: 120px; }
		@media (max-width: 600px) {
			.hk-stk-row { grid-template-columns: 1fr auto 24px; }
			.hk-stk-input { width: 110px; }
		}`;
		$(`<style id="hk-stk-css">${css}</style>`).appendTo("head");
	}
}
