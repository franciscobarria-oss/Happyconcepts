// Device detection for the desk (hooks.app_include_js).
//
// Tags <html> with hk-device-desktop | hk-device-tablet | hk-device-phone (and data-hk-device),
// so public/css/hk_tablet.css can restyle for touch screens. Desktop is never changed.
// Tablet = touch as the main pointer AND a screen at least 600 px on its short side
// (a touch laptop has a fine pointer, so it stays desktop). Phones keep Frappe's own mobile layout.
// Override for testing: add ?device=tablet|desktop|phone to any URL (remembered), ?device=auto clears it.
// Tablet-only behaviour goes in onTablet() below (empty for now).
(function () {
	const KEY = "hk_device";

	// Pure rule, tested by tests/test_device.py through node.
	function classify(w, h, coarse) {
		if (!coarse) return "desktop";
		return Math.min(w, h) < 600 ? "phone" : "tablet";
	}
	if (typeof module !== "undefined" && module.exports) {
		module.exports = { classify };
		return;
	}

	const root = document.documentElement;
	const NAMES = ["tablet", "desktop", "phone"];
	const saved = () => {
		try {
			return localStorage.getItem(KEY);
		} catch (e) {
			return null;
		}
	};
	try {
		const q = new URLSearchParams(location.search).get("device");
		if (q === "auto") localStorage.removeItem(KEY);
		else if (NAMES.includes(q)) localStorage.setItem(KEY, q);
	} catch (e) {
		/* private mode: the automatic value applies */
	}

	function detect() {
		const forced = saved();
		if (NAMES.includes(forced)) return forced;
		const coarse = !!(window.matchMedia && matchMedia("(pointer: coarse)").matches);
		// the screen is the device; innerWidth would shrink in split view
		const w = (window.screen && screen.width) || innerWidth;
		const h = (window.screen && screen.height) || innerHeight;
		return classify(w, h, coarse);
	}

	// Tablet-only JS goes here. Called on every change of device and on each page change.
	function onTablet() {}

	let last = null;
	function apply() {
		const d = detect();
		NAMES.forEach((n) => root.classList.toggle("hk-device-" + n, n === d));
		root.dataset.hkDevice = d;
		window.hk_device = d;
		if (d === "tablet") onTablet();
		if (d !== last) {
			last = d;
			if (window.$) $(document).trigger("hk-device", [d]);
		}
	}

	apply();
	window.addEventListener("resize", apply);
	window.addEventListener("orientationchange", apply);
	const later = () => {
		apply();
		if (window.$) $(document).on("page-change", apply);
	};
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", later);
	else later();
})();
