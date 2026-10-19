// Custom HTML Block "HK Clock In": kitchen tablet kiosk. Tap name, enter a 4-digit PIN, and the
// server records an Employee Checkin (IN, or OUT after an IN). PINs are checked on the server
// (hk_operations/team_api.clock_in); hashes and pay never reach the tablet. Bilingual EN / 中.
(async () => {
	const $ = (sel) => root_element.querySelector(sel);
	const API = "happy_kitchen.hk_operations.team_api.";
	const SHIFT_LABEL = { Early: "Early 早更 07:00", Late: "Late 晚更 11:00" };
	const hhmm = (dt) => (dt || "").slice(11, 16);
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	let emps = [];
	let current = null;
	let pin = "";
	let resetTimer = null;

	async function load() {
		emps = await frappe.xcall(API + "kiosk_status");
		renderTiles();
	}

	function renderTiles() {
		$(".clock").textContent = frappe.datetime.now_time().slice(0, 5);
		$(".tiles").innerHTML = emps.map((e) => {
			let sub = `<span class="muted">Off 休息</span>`;
			let cls = "";
			if (e.last_log_type === "IN") { sub = `<span class="in">In 上班 ${hhmm(e.last_time)}</span>`; cls = "is-in"; }
			else if (e.last_log_type === "OUT") sub = `<span class="muted">Out 下班 ${hhmm(e.last_time)}</span>`;
			else if (e.shift) sub = `<span class="muted">${esc(SHIFT_LABEL[e.shift] || e.shift)}</span>`;
			return `<button class="tile ${cls}" data-emp="${esc(e.name)}"><span class="nm">${esc(e.label)}</span>${sub}</button>`;
		}).join("") || `<p class="muted">No staff yet 未有員工</p>`;
	}

	function show(view) {
		for (const v of ["tiles-view", "pin-view", "done-view"]) $("." + v).hidden = v !== view;
		clearTimeout(resetTimer);
		if (view !== "tiles-view") resetTimer = setTimeout(() => show("tiles-view"), view === "done-view" ? 4000 : 30000);
		if (view === "tiles-view") { current = null; pin = ""; load(); }
	}

	function openPin(id) {
		current = emps.find((e) => e.name === id);
		if (!current) return;
		pin = "";
		$(".pin-name").textContent = current.label;
		$(".pin-action").textContent = current.last_log_type === "IN" ? "Clock out 下班打卡" : "Clock in 上班打卡";
		$(".pin-msg").textContent = current.has_pin ? "Enter your PIN 請輸入密碼" : "No PIN set yet. Ask your manager. 未設定密碼，請聯絡經理";
		drawDots();
		show("pin-view");
	}

	function drawDots() {
		$(".dots").innerHTML = [0, 1, 2, 3].map((i) => `<span class="dot ${i < pin.length ? "on" : ""}"></span>`).join("");
	}

	async function submitPin() {
		let r;
		try {
			r = await frappe.xcall(API + "clock_in", { employee: current.name, pin });
		} catch (e) {
			pin = "";
			drawDots();
			$(".pin-msg").textContent = "Couldn't save. Ask your manager. 未能儲存，請聯絡經理";
			return;
		}
		if (!r.ok) {
			pin = "";
			drawDots();
			$(".pin-msg").textContent = "Wrong PIN, try again 密碼錯誤，請再試";
			$(".dots").classList.add("shake");
			setTimeout(() => $(".dots").classList.remove("shake"), 400);
			return;
		}
		const hour = Number(r.time.slice(11, 13));
		const hello = r.log_type === "OUT" ? "See you, 再見" : hour < 12 ? "Good morning, 早晨" : "Hello, 你好";
		$(".done-title").textContent = `${hello} ${current.label}`;
		$(".done-sub").textContent = `${r.log_type === "IN" ? "Clocked in 已上班打卡" : "Clocked out 已下班打卡"} · ${hhmm(r.time)}`;
		$(".done-view").classList.toggle("out", r.log_type === "OUT");
		show("done-view");
	}

	root_element.addEventListener("click", (ev) => {
		const tile = ev.target.closest(".tile");
		if (tile) return openPin(tile.dataset.emp);
		const key = ev.target.closest("[data-key]");
		if (key && current && current.has_pin) {
			const k = key.dataset.key;
			if (k === "del") pin = pin.slice(0, -1);
			else if (pin.length < 4) pin += k;
			drawDots();
			if (pin.length === 4) submitPin();
			return;
		}
		if (ev.target.closest(".back") || ev.target.closest(".done-view")) show("tiles-view");
	});

	$(".keys").innerHTML = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"].map((k) =>
		k === "" ? "<span></span>" : `<button class="key" data-key="${k}">${k === "del" ? "⌫" : k}</button>`).join("");
	show("tiles-view");
	clearInterval(window.__hkClockTimer);
	window.__hkClockTimer = setInterval(() => { if (!current) load(); }, 60000);
})();
