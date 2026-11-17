// Item list: always shows Supplier / Buying Price (fields hk_list_supplier / hk_list_price), whatever columns a user
// saved earlier or the column limit would cut, and hides the whole right-hand column (time, comments, like).
(function () {
	const FIELDS = ["hk_list_supplier", "hk_list_price"];
	const settings = (frappe.listview_settings["Item"] = frappe.listview_settings["Item"] || {});
	const onload = settings.onload;

	function with_price_columns(listview) {
		const original = listview.setup_columns.bind(listview);
		listview.setup_columns = function () {
			original();
			const mine = FIELDS.map((f) => frappe.meta.get_docfield("Item", f)).filter(Boolean);
			if (!mine.length) return;
			const before = this.columns.length;
			const rest = this.columns.filter((c) => !(c.df && FIELDS.includes(c.df.fieldname)));
			// after the first columns (item name, tag, status), then trim from the end to the old width
			const at = Math.min(rest.length, 3);
			const added = mine.map((df) => ({ type: "Field", df }));
			const out = rest.slice(0, at).concat(added, rest.slice(at));
			while (out.length > before && out.length > at + added.length) out.pop();
			this.columns = out;
		};
		listview.setup_columns();
		listview.render_header(true);
		listview.refresh();
	}

	settings.onload = function (listview) {
		if (onload) onload.call(this, listview);
		listview.page.wrapper.addClass("hk-item-list");
		if (!document.getElementById("hk-item-list-css")) {
			const css = document.createElement("style");
			css.id = "hk-item-list-css";
			css.textContent =
				".hk-item-list .list-row-activity, .hk-item-list .list-row-head .list-liked-by-me," +
				".hk-item-list .list-row-head .level-right { display: none !important; }";
			document.head.appendChild(css);
		}
		with_price_columns(listview);
	};
})();
