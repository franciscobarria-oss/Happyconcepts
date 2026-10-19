// Happy Kitchen desk add-ons, loaded on every desk page (hooks.app_include_js).
//
// 1. Happy Concepts theme switch. The CSS (public/css/hk_theme.css) is always loaded
//    but only applies under html.hk-theme, added when the site has Recipe Settings >
//    "Happy Concepts desk theme" ticked (frappe.boot.hk_theme, see happy_kitchen/theme.py).
//    The last state is remembered per browser so the page doesn't flash stock colours.
// 2. EN / 中 language toggle: top right of every page header on desktop, bottom of the
//    side menu on mobile. Switches the user's language between English and Traditional
//    Chinese (theme.set_language) and reloads.
// 3. Sidebar labels through __(), which Frappe's v16 sidebar doesn't do itself.
(function () {
	const KEY = "hk-theme";
	const root = document.documentElement;

	// ---------- 1. theme ----------
	const setTheme = (on) => {
		root.classList.toggle("hk-theme", !!on);
		try {
			localStorage.setItem(KEY, on ? "1" : "0");
		} catch (e) {
			/* private mode: fine, the boot value still applies */
		}
	};
	try {
		if (localStorage.getItem(KEY) === "1") root.classList.add("hk-theme");
	} catch (e) {
		/* ignore */
	}
	const themeFromBoot = () => {
		if (window.frappe && frappe.boot && "hk_theme" in frappe.boot) {
			setTheme(frappe.boot.hk_theme);
			return true;
		}
		return false;
	};

	// ---------- 2. language toggle ----------
	const LANGS = [
		["en", "EN", "English"],
		["zh-TW", "中", "繁體中文"],
	];
	const currentLang = () => (window.frappe && frappe.boot && frappe.boot.lang) || "en";
	const isZh = () => currentLang().toLowerCase().startsWith("zh");

	function toggleHtml(where) {
		const zh = isZh();
		return `<div class="hk-lang hk-lang--${where}" role="group" aria-label="Language / 語言">${LANGS.map(
			([code, short, name]) => {
				const on = code === "zh-TW" ? zh : !zh;
				return `<button type="button" data-lang="${code}" aria-pressed="${on}" title="${name}">${short}</button>`;
			}
		).join("")}</div>`;
	}

	async function switchTo(lang) {
		if ((lang === "zh-TW") === isZh()) return;
		try {
			await frappe.call({ method: "happy_kitchen.theme.set_language", args: { lang }, freeze: true });
			window.location.reload();
		} catch (e) {
			/* frappe.call already showed the error */
		}
	}

	document.addEventListener("click", (e) => {
		const btn = e.target.closest(".hk-lang button[data-lang]");
		if (!btn) return;
		e.preventDefault();
		switchTo(btn.dataset.lang);
	});

	function placeToggles() {
		// desktop: right-hand side of each page header, before the "..." menu
		document.querySelectorAll(".page-head .standard-items-section").forEach((el) => {
			if (!el.querySelector(".hk-lang")) el.insertAdjacentHTML("afterbegin", toggleHtml("head"));
		});
		// mobile: bottom of the side menu, above the user menu
		document.querySelectorAll(".body-sidebar-bottom").forEach((el) => {
			if (el.querySelector(".hk-lang")) return;
			const user = el.querySelector(".dropdown-navbar-user");
			if (user) user.insertAdjacentHTML("beforebegin", toggleHtml("sidebar"));
			else el.insertAdjacentHTML("beforeend", toggleHtml("sidebar"));
		});
	}

	// ---------- 3. labels Frappe v16 leaves untranslated ----------
	// sidebar item labels, and free text in workspace paragraph / heading blocks
	// (view mode only: in edit mode the editor must keep the stored English).
	function translateStatic() {
		if (!isZh()) return;
		document.querySelectorAll(".body-sidebar .sidebar-item-label").forEach((el) => {
			if (el.dataset.hkSrc !== undefined || el.children.length) return;
			const src = el.textContent.trim();
			el.dataset.hkSrc = src;
			const t = __(src);
			if (t !== src) el.textContent = t;
		});
		document
			.querySelectorAll('.codex-editor .ce-paragraph:not([contenteditable="true"]), .codex-editor .ce-header:not([contenteditable="true"])')
			.forEach((el) => {
				if (el.dataset.hkDone) return;
				el.dataset.hkDone = "1";
				const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
				for (let n = walker.nextNode(); n; n = walker.nextNode()) {
					const src = n.nodeValue.trim();
					if (!src) continue;
					const t = __(src);
					if (t !== src) n.nodeValue = n.nodeValue.replace(src, t);
				}
			});
	}

	// ---------- wiring ----------
	let queued = false;
	const refresh = () => {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			if (!window.frappe || !frappe.boot || !frappe.session || frappe.session.user === "Guest") return;
			placeToggles();
			translateStatic();
		});
	};
	const start = () => {
		themeFromBoot();
		refresh();
		new MutationObserver(refresh).observe(document.body, { childList: true, subtree: true });
	};
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
	else start();
	if (window.$) $(document).on("startup", () => {
		themeFromBoot();
		refresh();
	});
})();
