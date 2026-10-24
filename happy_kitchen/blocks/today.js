// Custom HTML Block "HK Today" (synced from happy_kitchen/blocks/ on migrate): the Today home.
// KPIs, what is happening today, orders by day (with the A4 production sheet), waiting on you,
// then the tasks in three columns (ordering, receiving, production). "Simple | Detailed" is
// remembered per device; the page refreshes itself every 5 minutes so it can stay open on a
// kitchen screen. Runs inside the block's shadow root; `root_element` is provided by Frappe.
(() => {
	const $ = (sel) => root_element.querySelector(sel);
	const $$ = (sel) => [...root_element.querySelectorAll(sel)];
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const money = (v) => format_currency(v, frappe.boot.sysdefaults.currency, 0);
	const num = (v, p = 2) => format_number(v, null, p).replace(/\.0+$|(\.\d*?)0+$/, "$1");
	const day = (d) => `${__(moment(d).format("ddd"))} ${frappe.datetime.str_to_user(d)}`;
	const SHEET = "/api/method/happy_kitchen.recipe_management.production_sheet.sheet";
	const REFRESH_MS = 5 * 60 * 1000;
	const WAIT_SIMPLE = 4; // rows on "Waiting on you" in the simple view
	const TONES = { success: 1, info: 1, warning: 1, danger: 1 };
	// "List/Purchase Order?status=Open" -> frappe.set_route("List", "Purchase Order", {status: "Open"})
	const go = (route) => {
		const [path, query] = route.split("?");
		const args = path.split("/");
		if (query) {
			// a value that starts with "[" is a JSON filter, e.g. hk_email_order=["is","set"]
			const f = Object.fromEntries(new URLSearchParams(query));
			for (const k in f) if (f[k].startsWith("[")) { try { f[k] = JSON.parse(f[k]); } catch (e) { /* keep the text */ } }
			args.push(f);
		}
		frappe.set_route(...args);
	};
	// static English text in the HTML -> the user's language (EN / 中 toggle)
	$$("[data-t]").forEach((el) => (el.textContent = __(el.textContent.trim())));
	$(".sheet").href = `${SHEET}?date=${frappe.datetime.get_today()}`;

	// --- simple / detailed, remembered per device ---
	const STORE = "hk_today_view";
	let view = "simple";
	try {
		view = localStorage.getItem(STORE) === "detailed" ? "detailed" : "simple";
	} catch (e) {
		/* private window: not remembered */
	}
	const apply = () => {
		$(".hk").classList.toggle("detailed", view === "detailed");
		$$(".seg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === view));
	};
	apply();

	let data = null;
	root_element.addEventListener("click", (e) => {
		const seg = e.target.closest(".seg button");
		if (seg) {
			view = seg.dataset.view;
			try {
				localStorage.setItem(STORE, view);
			} catch (err) {
				/* not remembered */
			}
			return apply();
		}
		if (e.target.closest(".expand-more")) {
			view = "detailed";
			return apply();
		}
		if (e.target.closest(".refresh")) return load();
		const po = e.target.closest("[data-po]");
		if (po) return make_po(po);
		const pick = e.target.closest("[data-pickup]");
		if (pick) return pick_up(pick);
		const closer = e.target.closest("[data-close]");
		if (closer) return close_date(closer);
		const el = e.target.closest("[data-route]");
		if (!el) return;
		e.preventDefault();
		go(el.dataset.route);
	});

	const row = (r) => `<a class="row" href="#" data-route="${esc(r.route)}">
		${r.badge ? `<span class="badge ${TONES[r.tone] ? r.tone : ""}">${esc(r.badge)}</span>` : ""}
		<span class="grow"><b>${esc(r.label)}</b><span class="cap">${esc(r.detail)}</span></span>
		<span class="chev">›</span>
	</a>`;
	const empty = (t) => `<p class="empty">${esc(t)}</p>`;
	const show = (sel, rows, html, none) => {
		const el = $(sel);
		el.hidden = rows == null;
		if (rows == null) return;
		el.querySelector(".list").innerHTML = rows.length ? html : empty(none);
	};

	function render(d) {
		$(".date").textContent = `${__("Happy Kitchen")} · ${__(moment(d.today).format("dddd"))} ${frappe.datetime.str_to_user(d.today)}`;

		// KPI tiles: simple = figure + one line; detailed adds the breakdown
		$(".tiles").innerHTML = d.tiles
			.map((t) => `<button class="tile${TONES[t.tone] ? " " + t.tone : ""}" data-route="${esc(t.route)}">
				<span class="label">${esc(t.label)}</span><span class="value">${esc(t.value)}</span><span class="detail">${esc(t.detail)}</span>
				${(t.details || []).length ? `<span class="only-detail breakdown">${t.details
					.map((r) => `<span class="br"><span class="k">${esc(r.label)}</span><span class="v">${esc(r.value)}</span></span>`)
					.join("")}</span>` : ""}
			</button>`)
			.join("");

		// --- happening today ---
		const o = d.now.orders;
		show('[data-part="orders"]', o, (o || []).map((x) => {
			const l = x.labels; // label jobs: only once labels (P15) are installed
			const lab = !l ? "" : l.check ? `<span class="badge warning">${esc(__("Labels to check"))}</span>`
				: l.waiting ? `<span class="badge info">${esc(__("Labels printing"))}</span>`
				: l.printed ? `<span class="badge success">${esc(__("Labels printed"))}</span>` : "";
			return `<a class="row" href="#" data-route="Form/Sales Order/${esc(x.name)}">
				${x.late ? `<span class="badge danger">${esc(__("Late"))}</span>` : ""}
				<span class="grow"><b>${esc(x.customer)}</b><span class="cap">${esc(x.name)}${x.late ? " · " + esc(day(x.date)) : ""}</span>
					<span class="items only-detail">${x.items.slice(0, 6).map((i) => `<span>${esc(i)}</span>`).join("")}${x.items.length > 6 ? `<span>${esc(__("+{0} more", [x.items.length - 6]))}</span>` : ""}</span></span>
				${lab}
			</a>`;
		}).join(""), __("No orders going out today."));

		const p = d.now.production;
		show('[data-part="production"]', p, (p || []).map((x) => {
			const pct = x.units ? Math.min(100, Math.round((100 * x.made) / x.units)) : 100;
			return `<a class="row${x.done ? " done" : ""}" href="#" data-route="kitchen-production">
				<span class="grow"><b>${esc(x.name)}</b>
					<span class="cap">${esc(__("{0} of {1} made", [x.made_fmt, x.units_fmt]))} · ${esc(__("{0} batches", [x.batches]))}</span>
					<span class="bar"><i style="width:${pct}%"></i></span></span>
				${x.done ? `<span class="badge success">${esc(__("Done"))}</span>` : ""}
			</a>`;
		}).join(""), __("Nothing to make for today's orders."));

		const dl = d.now.deliveries;
		show('[data-part="deliveries"]', dl, (dl || []).map((x) => `<a class="row" href="#" data-route="receive-delivery/${esc(x.name)}">
			${x.late ? `<span class="badge danger">${esc(__("Late"))}</span>` : ""}
			<span class="grow"><b>${esc(x.supplier)}</b><span class="cap">${esc(x.name)} · ${esc(__("{0} lines", [x.lines]))} · ${esc(money(x.value))}${
				x.per_received ? " · " + esc(__("{0}% received", [Math.round(x.per_received)])) : ""}</span></span>
			<span class="chev">›</span>
		</a>`).join(""), __("No deliveries expected today."));

		const team = d.now.team;
		$('[data-part="team"]').hidden = team == null;
		if (team)
			$('[data-part="team"] .chips').innerHTML = team.length
				? team.map((t) => `<span class="chip ${t.state}"><span class="dot"></span>${esc(t.name)}
					<small>${esc(t.shift)}${t.since ? " · " + esc(t.state === "in" ? __("in since {0}", [t.since]) : __("out at {0}", [t.since])) : ""}</small></span>`).join("")
				: empty(__("No shifts on the roster today."));

		// --- orders by day: simple = one line per day (count, value, print); detailed = each order ---
		$('[data-part="days"]').hidden = !d.orders;
		if (d.orders) {
			const TONE = { late: "danger", today: "warning", tomorrow: "info", day_after: "info" };
			$(".days").innerHTML = d.orders
				.map((g) => {
					const when = g.date ? `${esc(__(moment(g.date).format("dddd")))} ${esc(frappe.datetime.str_to_user(g.date))}` : "";
					const rows = g.orders
						.map((o) => {
							const part = o.per_delivered > 0 ? ` · ${__("{0}% delivered", [Math.round(o.per_delivered)])}` : "";
							const date = g.key === "late" ? `${esc(frappe.datetime.str_to_user(o.delivery_date))} · ` : "";
							const items = (o.items || []).map((l) => `${esc(num(l.qty))} ${esc(l.uom)} ${esc(l.item_name)}`);
							if (o.more_items) items.push(esc(__("+{0} more", [o.more_items])));
							return `<a class="row" href="#" data-route="Form/Sales Order/${esc(o.name)}">
								<span class="grow"><b>${esc(o.customer)}</b> · ${esc(money(o.grand_total))}<span class="cap">${date}${esc(o.name)}${part}</span>${
									items.length ? `<span class="items">${items.map((t) => `<span>${t}</span>`).join("")}</span>` : ""
								}</span>
								<span class="chev">›</span>
							</a>`;
						})
						.join("");
					const more = g.count > g.orders.length ? `<p class="cap">${esc(__("and {0} more", [g.count - g.orders.length]))}</p>` : "";
					return `<div class="day ${g.key}">
						<div class="day-head"><span class="badge ${TONE[g.key] || "info"}">${esc(g.label)}</span><span class="cap">${when}${
							g.count ? `<span class="only-simple"> · ${esc(money(g.amount))}</span>` : ""
						}</span>${
							g.date ? `<a class="print" href="${SHEET}?date=${esc(g.date)}" target="_blank" rel="noopener" title="${esc(__("Production sheet"))}">${esc(__("Print A4"))}</a>` : ""
						}<span class="count">${g.count}</span></div>
						<div class="only-detail">${rows || `<p class="cap none">${esc(__("No orders"))}</p>`}${more}</div>
					</div>`;
				})
				.join("");
		}

		// --- email orders: what needs a person, and whether the Gmail pick-up is healthy ---
		const em = d.email;
		$('[data-part="email"]').hidden = !em;
		if (em) {
			const BUCKET = { late: __("Late"), today: __("Today"), tomorrow: __("Tomorrow"), after: __("Day after"), later: __("Later"), none: __("No date") };
			const h = em.health;
			const link = (route, text) => `<button type="button" class="btn small" data-route="${esc(route)}">${esc(text)}</button>`;
			$('[data-part="email"] .count').textContent = em.review + em.drafts;
			$('[data-part="email"] .list').innerHTML = [
				`<a class="row" href="#" data-route='List/Email Order?status=["in",["Needs review","Failed"]]&sales_order=["is","not set"]'>
					<span class="badge ${em.review ? "danger" : "success"}">${esc(em.review ? __("Check") : __("Done"))}</span>
					<span class="grow"><b>${esc(__("Emails to read by hand"))}: ${em.review}</b>${em.review_with_pdf
						? `<span class="cap">${esc(__("{0} have a PDF the reader could not use. Open the PDF and enter the order by hand.", [em.review_with_pdf]))}</span>` : ""}</span>
					<span class="chev">›</span></a>`,
				`<a class="row" href="#" data-route='List/Sales Order?docstatus=0&hk_email_order=["is","set"]'>
					<span class="badge ${em.drafts ? "warning" : "success"}">${esc(em.drafts ? __("To approve") : __("Done"))}</span>
					<span class="grow"><b>${esc(__("Draft orders from email to check"))}: ${em.drafts}</b>${em.buckets.length
						? `<span class="cap">${em.buckets.map((b) => esc(BUCKET[b.key]) + " " + b.count).join(" · ")}</span>` : ""}</span>
					<span class="chev">›</span></a>`,
				`<div class="row"><span class="badge ${h.tone === "ok" ? "success" : h.tone === "off" ? "" : h.tone}">${esc(h.tone === "ok" ? __("Working") : h.tone === "off" ? __("Off") : __("Check"))}</span>
					<span class="grow"><b>${esc(__(h.message))}</b><span class="cap">${esc(
						[h.last_checked ? __("Last check {0}", [h.last_checked.slice(5, 16)]) : "", h.error, em.new_mail + " " + __("new emails since yesterday"),
						 __("Label: {0}", [h.label]) + (h.extra_senders ? " + " + h.extra_senders : "")].filter(Boolean).join(" · ")
					)}</span></span>
					<span class="acts">${em.can_admin ? `<button type="button" class="btn small primary" data-pickup="1">${esc(__("Pick up orders now"))}</button>` : ""}
						${em.can_admin ? link("Form/Gmail Settings", __("Gmail Settings")) : ""}</span></div>`,
			].join("");
		}

		// --- waiting on you: simple = the first few, titles only; detailed = everything with the reason ---
		const w = d.waiting || [];
		$('[data-part="waiting"] .list').innerHTML = w.length
			? w.map((x, i) => `<a class="row${i >= WAIT_SIMPLE ? " only-detail" : ""}" href="#" data-route="${esc(x.route)}">
					<span class="badge ${TONES[x.tone] ? x.tone : ""}">${esc(
						__({ warning: "To approve", danger: "Check", info: "To do", success: "Done" }[x.tone] || "To do")
					)}</span>
					<span class="grow"><b>${esc(x.label)}</b><span class="cap only-detail">${esc(x.detail)}</span></span>
					<span class="chev">›</span>
				</a>`).join("") +
				(w.length > WAIT_SIMPLE ? `<button type="button" class="expand-more only-simple">${esc(__("+{0} more", [w.length - WAIT_SIMPLE]))}</button>` : "")
			: empty(__("All clear."));
		$('[data-part="waiting"] .count').textContent = w.length;

		// --- opened items and batches near their use-by date ---
		const useby = d.dates || [];
		$('[data-part="dates"]').hidden = d.dates == null;
		$('[data-part="dates"] .list').innerHTML = useby.length
			? useby.map((x, i) => `<div class="row">
					<span class="badge ${x.state === "past" || x.state === "today" ? "danger" : "warning"}">${esc(
						x.state === "past" ? __("Past use-by") : x.state === "today" ? __("Today") : __("Tomorrow"))}</span>
					<span class="grow"><b>${esc(x.item_name)}</b><span class="cap">${esc(x.kind === "Opened Item" ? __("Opened") : __("Batch"))}${x.lot ? " " + esc(x.lot) : ""} · ${esc(__("use by"))} ${esc(x.label)}</span></span>
					<span class="acts"><button type="button" class="btn small" data-close="${i}" data-action="Used up">${esc(__("Used up"))}</button>
					<button type="button" class="btn small primary" data-close="${i}" data-action="Discarded">${esc(__("Discarded"))}</button></span>
				</div>`).join("")
			: empty(__("Nothing is near its use-by date."));
		$('[data-part="dates"] .count').textContent = useby.length;

		// --- week ahead: one column per day, orders going out + deliveries coming in ---
		const wk = d.week;
		$('[data-part="week"]').hidden = !wk;
		if (wk) {
			const peak = Math.max(1, ...wk.days.map((x) => x.load));
			$('[data-part="week"] .legend').textContent = [wk.orders ? __("orders out") : "", wk.deliveries ? __("deliveries in") : ""].filter(Boolean).join(" + ");
			$(".week").innerHTML = wk.days.map((x, i) => {
				const tip = `${day(x.date)}: ${__("{0} orders", [x.orders])}, ${__("{0} deliveries", [x.deliveries])}${x.orders ? " · " + money(x.order_amount) : ""}`;
				const h = (n) => Math.round((100 * n) / peak);
				return `<div class="wk ${esc(x.level)}${i === 0 ? " today" : ""}" title="${esc(tip)}">
					<span class="n">${x.load}</span>
					<span class="stack"><i class="out" style="height:${h(x.orders)}%"></i><i class="in" style="height:${h(x.deliveries)}%"></i></span>
					<span class="dn">${esc(i === 0 ? __("Today") : __(moment(x.date).format("ddd")))}</span>
					<span class="lv">${x.level === "busy" ? esc(__("Busy day")) : x.level === "quiet" ? esc(__("Quiet day")) : "&nbsp;"}</span>
				</div>`;
			}).join("");
		}

		// --- tasks ---
		const ord = d.tasks.ordering;
		$('[data-task="ordering"]').hidden = !ord;
		if (ord) {
			let html = ord.groups.map((g, gi) => `<div class="supplier">
				<div class="top"><b>${esc(g.supplier_name || __("No default supplier"))}</b>
					<span class="badge ${g.need_by <= d.today ? "danger" : "warning"}">${esc(__("Needed {0}", [g.need_by <= d.today ? __("today") : day(g.need_by)]))}</span></div>
				<table>${g.lines.map((l) => `<tr><td><a href="/app/item/${encodeURIComponent(l.item)}">${esc(l.item_name)}</a>
					<span class="cap">${esc(__("short {0}", [l.short_fmt]))}${l.on_order ? " · " + esc(__("some already on order")) : ""}</span></td>
					<td class="num"><b>${esc(l.qty_fmt)}</b></td></tr>`).join("")}</table>
				${g.supplier && ord.can_create ? `<div class="acts"><button type="button" class="btn small primary" data-po="${gi}">${esc(__("Create draft order"))}</button></div>`
					: !g.supplier ? `<p class="cap">${esc(__("Set a default supplier on these items to order them from here."))}</p>` : ""}
			</div>`).join("");
			if (ord.drafts)
				html += row({ label: __("Purchase orders to send"), detail: __("{0} drafts", [ord.drafts]), route: "List/Purchase Order?docstatus=0", tone: "info", badge: __("To do") });
			$('[data-task="ordering"] .list').innerHTML = html || empty(__("Nothing to order for the next 3 days."));
			$('[data-task="ordering"] .count').textContent = ord.groups.reduce((n, g) => n + g.lines.length, 0) + (ord.drafts ? 1 : 0);
		}
		for (const key of ["receiving", "production"]) {
			const t = d.tasks[key];
			$(`[data-task="${key}"]`).hidden = !t;
			if (!t) continue;
			$(`[data-task="${key}"] .list`).innerHTML = t.length ? t.map(row).join("")
				: empty(key === "receiving" ? __("Nothing to receive today or tomorrow.") : __("Nothing left to make today."));
			$(`[data-task="${key}"] .count`).textContent = t.length;
		}
		$(".updated").textContent = __("Updated {0}", [moment().format("HH:mm")]);
	}

	async function close_date(btn) {
		const x = data.dates[Number(btn.dataset.close)];
		const action = btn.dataset.action;
		const send = async (v) => {
			await frappe.call({
				method: "happy_kitchen.hk_operations.dates_api.close",
				args: { kind: x.kind, name: x.name, row: x.row, action, qty: v && v.qty, uom: v && v.uom },
				freeze: true,
			});
			if (action === "Discarded") frappe.show_alert({ message: __("Thrown away and logged as wastage"), indicator: "green" });
			load();
		};
		if (action === "Used up") return send();
		frappe.prompt(
			[
				{ fieldname: "qty", fieldtype: "Float", label: __("How much was thrown away?"), reqd: 1 },
				{ fieldname: "uom", fieldtype: "Select", label: __("Unit"), options: "g\nkg\nml\nl\npiece", default: x.uom, reqd: 1 },
			],
			send,
			__("Discard {0}", [x.item_name])
		);
	}

	async function pick_up(btn) {
		btn.disabled = true;
		try {
			const r = await frappe.call({ method: "happy_kitchen.hk_operations.gmail_orders.fetch_now", freeze: true });
			const m = r.message || {};
			frappe.show_alert({ message: __("{0} new emails read", [m.new || 0]), indicator: m.failed ? "orange" : "green" });
			load();
		} catch (e) {
			btn.disabled = false;
		}
	}

	async function make_po(btn) {
		const g = data.tasks.ordering.groups[Number(btn.dataset.po)];
		btn.disabled = true;
		try {
			const r = await frappe.call({
				method: "happy_kitchen.recipe_management.today_board.create_purchase_order",
				args: { supplier: g.supplier, items: g.lines.map((l) => ({ item: l.item, qty: l.qty })), schedule_date: g.need_by },
				freeze: true,
			});
			frappe.show_alert({ message: __("Draft {0} created. Check it and submit it to send.", [r.message]), indicator: "green" });
			frappe.set_route("Form", "Purchase Order", r.message);
		} catch (e) {
			btn.disabled = false;
		}
	}

	async function load() {
		try {
			data = (await frappe.call("happy_kitchen.recipe_management.today.today")).message;
		} catch (e) {
			$(".tiles").innerHTML = `<div class="note"><b>${esc(__("Couldn't load today's figures."))}</b> ${esc(__("Reload the page to try again."))}</div>`;
			return;
		}
		render(data);
	}
	load();
	const timer = setInterval(() => {
		if (!root_element.isConnected) return clearInterval(timer);
		if (document.visibilityState === "visible") load();
	}, REFRESH_MS);
})();
