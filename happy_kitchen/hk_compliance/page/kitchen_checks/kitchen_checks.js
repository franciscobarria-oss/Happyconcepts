// Kitchen Checks tablet screen: today's checklists for one area, answer each question (saved as
// you tap), then sign with name + 4-digit PIN. Rules run on the server (hk_compliance/api.py);
// PIN hashes never reach the tablet. Bilingual EN / 中 like the Clock In kiosk.
(() => {
const API = "happy_kitchen.hk_compliance.api.";
const AREA_KEY = "hk_checks_area";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const hhmm = (dt) => (dt || "").slice(11, 16);
const store = {
	get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
	set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};

function css() {
	if (document.getElementById("hkc-css")) return;
	$(`<style id="hkc-css">
	.hkc { max-width: 900px; margin: 0 auto; padding-bottom: 120px; font-size: 16px; }
	.hkc-top { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-bottom: 12px; }
	.hkc-top select { min-height: 48px; font-size: 18px; border-radius: 12px; padding: 4px 12px; border: 1px solid var(--border-color); background: var(--control-bg); }
	.hkc-clock { font-size: 28px; font-weight: 700; }
	.hkc-band h4 { margin: 20px 0 8px; display: flex; gap: 8px; align-items: center; }
	.hkc-pill { border-radius: 99px; padding: 2px 10px; font-size: 13px; font-weight: 600; }
	.hkc-band.overdue .hkc-pill { background: var(--red-100); color: var(--red-700); }
	.hkc-band.due .hkc-pill { background: var(--orange-100); color: var(--orange-700); }
	.hkc-band.later .hkc-pill { background: var(--gray-100); color: var(--gray-700); }
	.hkc-band.done .hkc-pill { background: var(--green-100); color: var(--green-700); }
	.hkc-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
	.hkc-card { text-align: left; min-height: 76px; padding: 12px 16px; border-radius: 14px; border: 1px solid var(--border-color); background: var(--card-bg); width: 100%; }
	.hkc-band.overdue .hkc-card { border-left: 6px solid var(--red-500); }
	.hkc-band.due .hkc-card { border-left: 6px solid var(--orange-400); }
	.hkc-band.done .hkc-card { border-left: 6px solid var(--green-500); }
	.hkc-card b { font-size: 18px; display: block; }
	.hkc-muted { color: var(--text-muted); font-size: 14px; }
	.hkc-q { border: 1px solid var(--border-color); border-radius: 14px; padding: 14px 16px; margin: 10px 0; background: var(--card-bg); }
	.hkc-q.fail { border-color: var(--red-500); box-shadow: 0 0 0 2px var(--red-100); }
	.hkc-q.pass { border-color: var(--green-500); }
	.hkc-q .p { font-size: 18px; font-weight: 600; }
	.hkc-q .zh { font-size: 16px; color: var(--text-muted); }
	.hkc-opts { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
	.hkc-opt { min-width: 110px; min-height: 56px; font-size: 18px; border-radius: 12px; border: 1px solid var(--border-color); background: var(--control-bg); padding: 0 16px; }
	.hkc-opt.on { background: var(--primary); color: #fff; border-color: var(--primary); }
	.hkc-opt.on.bad { background: var(--red-500); border-color: var(--red-500); }
	.hkc-in { min-height: 56px; font-size: 22px; border-radius: 12px; border: 1px solid var(--border-color); padding: 6px 14px; background: var(--control-bg); width: 180px; }
	.hkc-text { width: 100%; min-height: 64px; font-size: 16px; border-radius: 12px; border: 1px solid var(--border-color); padding: 8px 12px; background: var(--control-bg); }
	.hkc-fix { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--red-300); }
	.hkc-chip { min-height: 44px; border-radius: 99px; border: 1px solid var(--border-color); background: var(--control-bg); padding: 0 14px; margin: 0 6px 6px 0; font-size: 15px; }
	.hkc-photo img { max-width: 160px; max-height: 120px; border-radius: 10px; margin-top: 8px; display: block; }
	.hkc-big { width: 100%; min-height: 66px; font-size: 22px; border-radius: 14px; margin-top: 16px; }
	.hkc-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; margin-top: 12px; }
	.hkc-tile { min-height: 72px; border-radius: 14px; border: 1px solid var(--border-color); background: var(--card-bg); font-size: 18px; font-weight: 600; }
	.hkc-tile small { display: block; font-weight: 400; color: var(--text-muted); font-size: 13px; }
	.hkc-dots { display: flex; gap: 14px; justify-content: center; margin: 16px 0; }
	.hkc-dot { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--gray-500); }
	.hkc-dot.on { background: var(--gray-800); border-color: var(--gray-800); }
	.hkc-keys { display: grid; grid-template-columns: repeat(3, 88px); gap: 12px; justify-content: center; }
	.hkc-key { height: 72px; font-size: 28px; border-radius: 14px; border: 1px solid var(--border-color); background: var(--card-bg); }
	.hkc-center { text-align: center; }
	.hkc-err { color: var(--red-600); margin: 8px 0; }
	.hkc-done { font-size: 72px; color: var(--green-500); }
	</style>`).appendTo("head");
}

frappe.pages["kitchen-checks"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: "Kitchen Checks 廚房檢查", single_column: true });
	css();
	wrapper.hkc = new Checks(wrapper);
};
frappe.pages["kitchen-checks"].on_page_show = (wrapper) => wrapper.hkc.show();

class Checks {
	constructor(wrapper) {
		this.$b = $(wrapper).find(".layout-main-section");
		this.$b.html(`<div class="hkc"></div>`);
		this.$m = this.$b.find(".hkc");
		this.area = store.get(AREA_KEY);
		this.run = null;
		this.signer = null;
		this.pin = "";
		this.$m.on("click", (e) => this.click(e));
		// typed answers save when the field loses focus; photos when the camera returns
		const idx = (el) => Number($(el).closest(".hkc-q").data("idx"));
		this.$m.on("change", ".hkc-num, .hkc-val", (e) => this.save(idx(e.target), { value: $(e.target).val() }));
		this.$m.on("change", ".hkc-corr", (e) => this.save(idx(e.target), { corrective_action: $(e.target).val() }));
		this.$m.on("change", ".hkc-file", (e) => { if (e.target.files && e.target.files[0]) this.photo(idx(e.target), e.target.files[0]); });
	}

	async show() {
		this.areas = await frappe.xcall(API + "areas");
		if (!this.areas.length) { this.$m.html(`<p>No areas yet. A manager adds them under Check Area. 未有區域</p>`); return; }
		if (!this.areas.some((a) => a.name === this.area)) this.area = this.areas[0].name;
		this.list();
		clearInterval(this.timer);
		this.timer = setInterval(() => { if (!this.run && document.body.contains(this.$m[0])) this.list(); }, 60000);
	}

	// ---------------------------------------------------------------- task list
	async list() {
		this.run = null;
		const t = await frappe.xcall(API + "today_tasks", { area: this.area });
		const opts = this.areas.map((a) => `<option value="${esc(a.name)}" ${a.name === this.area ? "selected" : ""}>${esc(a.name)} ${esc(a.area_name_zh || "")}</option>`).join("");
		const card = (r, kind) => {
			let sub = "";
			if (kind === "done") sub = `${esc(r.employee_name || "")} · ${hhmm(r.signed_at)}${r.late ? " · Late 遲" : ""}${r.issues ? ` · ⚠ ${r.issues}` : ""}`;
			else if (kind === "later") sub = `Starts 開始 ${hhmm(r.window_start)} · Due 限時 ${hhmm(r.window_end)}`;
			else sub = `Due 限時 ${hhmm(r.window_end)}${r.status === "Missed" ? " · Missed 已錯過" : r.status === "In progress" ? " · Started 已開始" : ""}`;
			const data = kind === "later" ? `data-schedule="${esc(r.schedule)}" data-start="${esc(r.window_start)}"` : `data-run="${esc(r.name)}"`;
			return `<button class="hkc-card" ${data}><b>${esc(r.title)}</b>${r.title_zh ? `<span class="hkc-muted">${esc(r.title_zh)}</span><br>` : ""}<span class="hkc-muted">${sub}</span></button>`;
		};
		const band = (kind, label, rows) => rows.length ? `<div class="hkc-band ${kind}"><h4>${label} <span class="hkc-pill">${rows.length}</span></h4>
			<div class="hkc-cards">${rows.map((r) => card(r, kind)).join("")}</div></div>` : "";
		const empty = !t.overdue.length && !t.due.length && !t.later.length && !t.done.length;
		this.$m.html(`<div class="hkc-top"><select class="hkc-area">${opts}</select><span class="hkc-clock">${hhmm(t.now)}</span></div>
			${band("overdue", "Overdue 逾時", t.overdue)}${band("due", "Due now 現在要做", t.due)}
			${band("later", "Later today 稍後", t.later)}${band("done", "Done today 今日已完成", t.done)}
			${empty ? `<p class="hkc-muted">Nothing scheduled for this area today. 今日此區域沒有檢查</p>` : ""}`);
		this.$m.find(".hkc-area").on("change", (e) => { this.area = e.target.value; store.set(AREA_KEY, this.area); this.list(); });
	}

	// ---------------------------------------------------------------- one checklist
	async open(name) {
		this.run = await frappe.xcall(API + "get_run", { name });
		this.drawRun();
	}

	drawRun() {
		const r = this.run;
		const locked = r.docstatus !== 0;
		const q = r.answers.map((a) => this.question(a, locked)).join("");
		this.$m.html(`<button class="btn btn-default hkc-back">‹ Back 返回</button>
			<h3 style="margin:12px 0 0">${esc(r.title)} <span class="hkc-muted">${esc(r.title_zh || "")}</span></h3>
			<div class="hkc-muted">${esc(r.area)}${r.window_end ? ` · Due 限時 ${hhmm(r.window_end)}` : ""}
			${locked ? ` · Signed by 簽署 ${esc(r.employee_name)} ${hhmm(r.signed_at)}` : ""}</div>
			${q}<div class="hkc-err hkc-problems"></div>
			${locked ? "" : `<button class="btn btn-primary hkc-big hkc-sign">Sign off 簽署完成</button>`}`);
	}

	question(a, locked) {
		const val = a.value || "";
		const dis = locked ? "disabled" : "";
		let input = "";
		if (a.answer_type === "Yes/No") {
			input = ["Yes", "No"].map((v) => `<button class="hkc-opt ${val === v ? "on" : ""} ${val === v && a.result === "Fail" ? "bad" : ""}" data-val="${v}" ${dis}>${v === "Yes" ? "Yes 是" : "No 否"}</button>`).join("");
		} else if (a.answer_type === "Choice") {
			input = a.choices.map((v) => `<button class="hkc-opt ${val === v ? "on" : ""} ${val === v && a.result === "Fail" ? "bad" : ""}" data-val="${esc(v)}" ${dis}>${esc(v)}</button>`).join("");
		} else if (a.answer_type === "Number") {
			input = `<input class="hkc-in hkc-num" type="number" inputmode="decimal" step="any" value="${esc(val)}" ${dis}> <span>${esc(a.unit || "")}</span>`;
		} else if (a.answer_type === "Text") {
			input = `<textarea class="hkc-text hkc-val" ${dis}>${esc(val)}</textarea>`;
		}
		const wantsPhoto = a.answer_type === "Photo" || a.photo_required;
		const photo = wantsPhoto || a.photo ? `<div class="hkc-photo">${a.photo ? `<img src="${esc(a.photo)}">` : ""}
			${locked ? "" : `<label class="btn btn-default" style="margin-top:8px">📷 ${a.photo ? "Retake 重拍" : "Take photo 拍照"}
			<input type="file" accept="image/*" capture="environment" class="hkc-file" hidden></label>`}</div>` : "";
		const presets = (this.run.presets || []).map((p) => `<button class="hkc-chip" data-fix="${esc(p.action)}" ${dis}>${esc(p.action)} ${esc(p.action_zh || "")}</button>`).join("");
		const fix = a.result === "Fail" ? `<div class="hkc-fix"><b>What did you do about it? 你做了甚麼跟進?</b><div style="margin:8px 0">${presets}</div>
			<textarea class="hkc-text hkc-corr" ${dis}>${esc(a.corrective_action || "")}</textarea></div>` : "";
		const opt = a.required ? "" : ` <span class="hkc-muted">(optional 可選)</span>`;
		return `<div class="hkc-q ${a.result === "Fail" ? "fail" : a.result === "Pass" ? "pass" : ""}" data-idx="${a.idx}">
			<div class="p">${a.idx}. ${esc(a.prompt)}${a.critical ? " ⚠" : ""}${opt}</div>${a.prompt_zh ? `<div class="zh">${esc(a.prompt_zh)}</div>` : ""}
			${a.limits ? `<div class="hkc-muted">Allowed 合格範圍: ${esc(a.limits)}</div>` : ""}${a.help ? `<div class="hkc-muted">${esc(a.help)}</div>` : ""}
			<div class="hkc-opts">${input}</div>${photo}${fix}</div>`;
	}

	async save(idx, args) {
		try {
			const r = await frappe.xcall(API + "save_answer", { name: this.run.name, idx, ...args });
			const a = this.run.answers.find((x) => x.idx === idx);
			Object.assign(a, args, { result: r.result });
			this.redrawQuestion(a);
		} catch (e) {
			frappe.show_alert({ message: "Not saved, try again 未儲存，請再試", indicator: "red" });
		}
	}

	redrawQuestion(a) {
		const $q = this.$m.find(`.hkc-q[data-idx="${a.idx}"]`);
		$q.replaceWith(this.question(a, false));
	}

	async photo(idx, file) {
		const data = await shrink(file, 1600);
		frappe.show_alert({ message: "Uploading photo 上載相片中…", indicator: "blue" });
		try {
			const r = await frappe.xcall(API + "upload_photo", { name: this.run.name, idx, data, filename: "photo.jpg" });
			const a = this.run.answers.find((x) => x.idx === idx);
			a.photo = r.photo; a.result = r.result;
			this.redrawQuestion(a);
		} catch (e) {
			frappe.show_alert({ message: "Photo not saved 相片未儲存", indicator: "red" });
		}
	}

	// ---------------------------------------------------------------- sign-off
	staff() {
		const tiles = this.run.staff.map((s) => `<button class="hkc-tile" data-emp="${esc(s.name)}">${esc(s.label)}
			<small>${s.on_shift ? "On shift 當更" : ""}${s.has_pin ? "" : " No PIN 未設密碼"}</small></button>`).join("");
		this.$m.html(`<button class="btn btn-default hkc-back-run">‹ Back 返回</button>
			<h3 style="margin-top:12px">Who is signing? 誰簽署?</h3><div class="hkc-tiles">${tiles || "No staff yet 未有員工"}</div>`);
	}

	pinPad(emp) {
		this.signer = this.run.staff.find((s) => s.name === emp);
		this.pin = "";
		const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"].map((k) =>
			k === "" ? "<span></span>" : `<button class="hkc-key" data-key="${k}">${k === "del" ? "⌫" : k}</button>`).join("");
		this.$m.html(`<button class="btn btn-default hkc-back-staff">‹ Back 返回</button><div class="hkc-center">
			<h3>${esc(this.signer.label)}</h3><p>Sign ${esc(this.run.title)} 簽署</p><div class="hkc-dots"></div>
			<p class="hkc-err hkc-pinmsg">${this.signer.has_pin ? "" : "No PIN set yet. Ask your manager. 未設定密碼，請聯絡經理"}</p>
			<div class="hkc-keys">${keys}</div></div>`);
		this.dots();
	}

	dots() {
		this.$m.find(".hkc-dots").html([0, 1, 2, 3].map((i) => `<span class="hkc-dot ${i < this.pin.length ? "on" : ""}"></span>`).join(""));
	}

	async sign() {
		let r;
		try {
			r = await frappe.xcall(API + "sign_off", { name: this.run.name, employee: this.signer.name, pin: this.pin });
		} catch (e) {
			this.pin = ""; this.dots();
			this.$m.find(".hkc-pinmsg").text("Couldn't sign. Ask your manager. 未能簽署，請聯絡經理");
			return;
		}
		if (r.wrong_pin) {
			this.pin = ""; this.dots();
			this.$m.find(".hkc-pinmsg").text("Wrong PIN, try again 密碼錯誤，請再試");
			return;
		}
		if (r.problems) { this.drawRun(); this.showProblems(r.problems); return; }
		const issues = r.issues ? `<p class="hkc-err">⚠ ${r.issues} failed: the manager will see what you did. ${r.issues} 項不合格，經理會查看跟進</p>` : "";
		this.$m.html(`<div class="hkc-center"><div class="hkc-done">✓</div><h3>Signed 已簽署 · ${esc(this.signer.label)}</h3>
			<p>${esc(this.run.title)} · ${hhmm(r.signed_at)}${r.late ? " · Late 遲" : ""}</p>${issues}
			<button class="btn btn-primary hkc-big hkc-back">Back to the list 返回清單</button></div>`);
		this.run = null;
		setTimeout(() => { if (!this.run) this.list(); }, 6000);
	}

	showProblems(list) {
		this.$m.find(".hkc-problems").html(`<b>Not finished yet 尚未完成:</b><br>${list.map(esc).join("<br>")}`);
		this.$m.find(".hkc-problems")[0].scrollIntoView({ behavior: "smooth" });
	}

	// ---------------------------------------------------------------- events
	async click(e) {
		const $t = $(e.target);
		const idxOf = () => Number($t.closest(".hkc-q").data("idx"));
		if ($t.closest(".hkc-back").length) return this.list();
		if ($t.closest(".hkc-back-run").length) return this.drawRun();
		if ($t.closest(".hkc-back-staff").length) return this.staff();
		const $card = $t.closest(".hkc-card");
		if ($card.length) {
			if ($card.data("run")) return this.open($card.data("run"));
			const name = await frappe.xcall(API + "start_early", { schedule_name: $card.data("schedule"), window_start: $card.data("start") });
			return this.open(name);
		}
		const $opt = $t.closest(".hkc-opt");
		if ($opt.length && !$opt.prop("disabled")) return this.save(idxOf(), { value: String($opt.data("val")) });
		const $chip = $t.closest(".hkc-chip");
		if ($chip.length) {
			const $c = $chip.closest(".hkc-q").find(".hkc-corr");
			$c.val(($c.val() ? $c.val() + "\n" : "") + $chip.data("fix"));
			return this.save(idxOf(), { corrective_action: $c.val() });
		}
		if ($t.closest(".hkc-sign").length) {
			// answers not yet saved by a blur/change event are saved first
			const missing = this.run.answers.filter((a) => a.required && !(a.answer_type === "Photo" ? a.photo : a.value));
			if (missing.length) return this.showProblems(missing.map((a) => `${a.idx}. ${a.prompt}: not answered 未回答`));
			return this.staff();
		}
		const $tile = $t.closest(".hkc-tile");
		if ($tile.length) return this.pinPad($tile.data("emp"));
		const $key = $t.closest(".hkc-key");
		if ($key.length && this.signer && this.signer.has_pin) {
			const k = String($key.data("key"));
			if (k === "del") this.pin = this.pin.slice(0, -1);
			else if (this.pin.length < 4) this.pin += k;
			this.dots();
			if (this.pin.length === 4) this.sign();
		}
	}
}

// shrink a camera photo to at most `max` px on the long side, as a JPEG data URL
function shrink(file, max) {
	return new Promise((resolve, reject) => {
		const img = new Image();
		img.onload = () => {
			const k = Math.min(1, max / Math.max(img.width, img.height));
			const c = document.createElement("canvas");
			c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
			c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
			URL.revokeObjectURL(img.src);
			resolve(c.toDataURL("image/jpeg", 0.8));
		};
		img.onerror = reject;
		img.src = URL.createObjectURL(file);
	});
}
})();
