// Tablet shell (hooks.app_include_js, after hk_device.js). Runs only when <html> has
// data-hk-device="tablet": a top bar with five tabs (Today, Production, Orders, Stock, More)
// replaces the side menu. Desktop and phone never get it. Layout: Figma "tablet simplified".
(function () {
	const root = document.documentElement;
	const __ = window.__ || ((s) => s); // literal __("...") calls are what the translation checker reads
	const tabs = () => [
		{ key: "today", label: __("Today"), route: "/app/today", match: ["today"] },
		{ key: "production", label: __("Production"), route: "/app/kitchen-production", match: ["kitchen-production", "kitchen-opened", "recipe", "recipes", "recipe-production-log", "wastage-log"] },
		{ key: "orders", label: __("Orders"), route: "/app/sales-order", match: ["sales-order", "email-order", "customer"] },
		{ key: "stock", label: __("Stock"), route: "/app/stock-take", match: ["stock-take", "stock-take-count", "stock-take-sheet", "item", "stock-ledger", "stock-reconciliation", "purchase-order", "purchase-receipt", "receive-delivery", "supplier"] },
	];
	// "More" opens this list (all pages that stay reachable on a tablet)
	const more = () => [
		[__("Team"), "/app/team"],
		[__("Clock In"), "/app/clock-in"],
		[__("Kitchen Checks"), "/app/kitchen-checks"],
		[__("Receive Delivery"), "/app/receive-delivery"],
		[__("Recipes"), "/app/recipes"],
		[__("Full desk"), "/desk"],
	];

	const routePart = () => {
		const p = location.pathname.replace(/^\/(app|desk)\/?/, "").split("/")[0];
		return p || "today";
	};
	// pages under the More tab (Figma: Team roster, Clock in and Kitchen checks sit there)
	const MORE_ROUTES = ["team", "clock-in", "kitchen-checks", "checklist-run", "checklist-template", "checklist-schedule", "employee", "roster"];
	const activeKey = () => {
		const r = routePart();
		if (MORE_ROUTES.includes(r)) return "more";
		const t = tabs().find((x) => x.match.includes(r));
		return t ? t.key : "";
	};
	const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

	function build() {
		const zh = String((window.frappe && frappe.boot && frappe.boot.lang) || "en").toLowerCase().startsWith("zh");
		const nav = document.createElement("nav");
		nav.className = "hk-tabbar";
		nav.setAttribute("aria-label", __("Main"));
		nav.innerHTML =
			`<a class="hk-tabbar-brand" href="/app/today">HAPPY KITCHEN</a><div class="hk-tabbar-tabs">` +
			tabs().map((t) => `<a class="hk-tab" data-key="${t.key}" href="${t.route}">${esc(t.label)}</a>`).join("") +
			`<span class="hk-more-wrap"><button type="button" class="hk-tab hk-tab-more" data-key="more" aria-expanded="false">${esc(__("More"))}</button>` +
			`<div class="hk-more" hidden>${more().map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join("")}</div></span></div>` +
			// EN / 中 toggle at the right end of the bar (Figma); hk_theme.js handles the click on .hk-lang button[data-lang]
			`<div class="hk-lang hk-lang--bar" role="group" aria-label="Language / 語言">` +
			[["en", "EN", "English"], ["zh-TW", "中", "繁體中文"]]
				.map(([c, t, n]) => `<button type="button" data-lang="${c}" aria-pressed="${(c === "zh-TW") === zh}" title="${n}">${t}</button>`)
				.join("") +
			`</div>`;
		nav.querySelector(".hk-tab-more").addEventListener("click", (e) => {
			e.stopPropagation();
			const box = nav.querySelector(".hk-more");
			box.hidden = !box.hidden;
			e.currentTarget.setAttribute("aria-expanded", String(!box.hidden));
		});
		nav.querySelector(".hk-more").addEventListener("click", () => (nav.querySelector(".hk-more").hidden = true));
		document.addEventListener("click", () => {
			const box = nav.querySelector(".hk-more");
			if (box) box.hidden = true;
		});
		return nav;
	}

	function sync() {
		const on = root.dataset.hkDevice === "tablet" && window.frappe && frappe.session && frappe.session.user !== "Guest";
		let nav = document.querySelector(".hk-tabbar");
		if (!on) {
			if (nav) nav.remove();
			return;
		}
		if (!nav && document.body) {
			nav = build();
			document.body.prepend(nav);
		}
		if (nav) {
			const k = activeKey();
			nav.querySelectorAll(".hk-tab").forEach((a) => a.classList.toggle("active", a.dataset.key === k));
		}
	}

	let queued = false;
	const refresh = () => {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			sync();
		});
	};
	const start = () => {
		refresh();
		new MutationObserver(refresh).observe(root, { attributes: true, attributeFilter: ["data-hk-device"] });
		window.addEventListener("popstate", refresh);
		if (window.$) $(document).on("page-change startup", refresh);
	};
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
	else start();
})();
