// Item list: Supplier / Buying Price columns come from the in_list_view fields hk_list_supplier / hk_list_price;
// the comment count and like heart on each row are hidden (class hk-item-list, styles below).
(function () {
	const settings = (frappe.listview_settings["Item"] = frappe.listview_settings["Item"] || {});
	const onload = settings.onload;
	settings.onload = function (listview) {
		if (onload) onload.call(this, listview);
		listview.page.wrapper.addClass("hk-item-list");
		if (!document.getElementById("hk-item-list-css")) {
			const css = document.createElement("style");
			css.id = "hk-item-list-css";
			css.textContent =
				".hk-item-list .comment-count, .hk-item-list .list-row-like, .hk-item-list .list-liked-by-me," +
				".hk-item-list .list-row-activity .comment-count, .hk-item-list .level-right .list-count + .list-liked-by-me," +
				".hk-item-list .list-row-head .list-liked-by-me, .hk-item-list .list-row-like-count { display: none !important; }";
			document.head.appendChild(css);
		}
	};
})();
