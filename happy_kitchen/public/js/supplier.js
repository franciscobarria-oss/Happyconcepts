// Supplier -> "Products" tab: items bought from this supplier with their buying price,
// and "+ Add Product", which creates or links an ING-xxx item on the server.
frappe.ui.form.on("Supplier", {
	refresh(frm) {
		hk_render_supplier_products(frm);
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Ingredients & Packaging"),
			() => frappe.set_route("query-report", "Ingredients and Packaging by Supplier", { supplier: frm.doc.name }),
			__("View")
		);
	},
});

async function hk_render_supplier_products(frm) {
	const field = frm.fields_dict.hk_products_html;
	if (!field) return;
	const $w = field.$wrapper;
	if (frm.is_new()) {
		$w.html(`<p class="text-muted">${__("Save the supplier to see its products.")}</p>`);
		return;
	}
	$w.html(`<p class="text-muted">${__("Loading products...")}</p>`);
	const items = (await frappe.xcall("happy_kitchen.hk_operations.purchasing.get_supplier_products", {
		supplier: frm.doc.name,
	})) || [];

	const esc = frappe.utils.escape_html;
	const cur = (v, d) => format_currency(v, frappe.defaults.get_default("currency"), d);
	const rows = items
		.map((it) => {
			const p = it.price;
			let price = `<span class="text-muted">${__("No price")}</span>`;
			if (p && p.uom === "Gram") {
				price = `<b>${cur(p.price_list_rate * 1000, 2)} / kg</b><br><small class="text-muted">${cur(p.price_list_rate, 4)} / g</small>`;
			} else if (p) {
				price = `<b>${cur(p.price_list_rate, 2)} / ${esc(p.uom === "Nos" ? __("pc") : p.uom)}</b>`;
			}
			const ordering = [
				flt(it.min_order_qty) ? `${__("min")} ${format_number(it.min_order_qty, null, 0)} ${esc(it.stock_uom)}` : "",
				flt(it.hk_order_multiple) ? `${__("multiples of")} ${format_number(it.hk_order_multiple, null, 0)}` : "",
			].filter(Boolean).join(" · ");
			const q = esc(`${it.name} ${it.item_name} ${it.item_group || ""}`.toLowerCase());
			return `<tr class="hk-sp-row${it.disabled ? " text-muted" : ""}" data-q="${q}">
				<td><a href="/app/item/${encodeURIComponent(it.name)}"><b>${esc(it.item_name)}</b></a><br><small class="text-muted">${esc(it.name)}</small></td>
				<td>${esc(__(it.item_group || ""))}</td>
				<td class="text-right" style="white-space:nowrap">${price}</td>
				<td class="text-right text-muted" style="white-space:nowrap">${ordering}</td>
			</tr>`;
		})
		.join("");

	const minimum = flt(frm.doc.hk_min_order_amount)
		? " · " + __("Minimum order: {0}", [cur(frm.doc.hk_min_order_amount, 2)]) : "";
	const header = `
		<div class="flex justify-between align-center" style="margin-bottom: var(--margin-sm); gap: 10px; flex-wrap: wrap">
			<span class="text-muted">${__("{0} products from this supplier", [items.length])}${minimum}</span>
			<span style="display:flex; gap:8px">
				<input type="search" class="form-control hk-sp-search" style="width:240px" placeholder="${__("Search products")}">
				<button class="btn btn-primary btn-sm hk-add-product">${__("+ Add Product")}</button>
			</span>
		</div>`;
	const body = items.length
		? `<table class="table table-hover"><thead><tr>
				<th>${__("Product")}</th><th>${__("Group")}</th>
				<th class="text-right">${__("Buying Price")}</th><th class="text-right">${__("Ordering")}</th>
			</tr></thead><tbody>${rows}</tbody></table>`
		: `<p class="text-muted">${__("No products are linked to this supplier yet.")}</p>`;

	$w.html(header + body);
	$w.find(".hk-sp-search").on("input", (e) => {
		const q = e.target.value.trim().toLowerCase();
		$w.find(".hk-sp-row").each((_, tr) => $(tr).toggle(!q || tr.dataset.q.includes(q)));
	});
	$w.find(".hk-add-product").on("click", () => hk_add_product_dialog(frm));
}

function hk_add_product_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Add Product from {0}", [frm.doc.name]),
		fields: [
			{ fieldname: "item_name", label: __("Name"), fieldtype: "Data", reqd: 1 },
			{ fieldname: "price", label: __("Price"), fieldtype: "Float", precision: 4, reqd: 1 },
			{
				fieldname: "uom", label: __("UOM"), fieldtype: "Select", reqd: 1, options: "Gram\nKg\nNos", default: "Gram",
				description: __("Price per unit. Kg prices are stored per gram (price ÷ 1000)."),
			},
			{
				fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group", reqd: 1,
				default: "Ingredients", get_query: () => ({ filters: { is_group: 0 } }),
			},
			{ fieldtype: "Section Break", label: __("Ordering (optional)") },
			{ fieldname: "min_order_qty", label: __("Minimum Order Qty"), fieldtype: "Float",
			  description: __("In the UOM above. 0 = no minimum.") },
			{ fieldtype: "Column Break" },
			{ fieldname: "order_multiple", label: __("Order in Multiples Of"), fieldtype: "Float",
			  description: __("In the UOM above, e.g. 12 for eggs by the dozen. 0 = any quantity.") },
		],
		primary_action_label: __("Add"),
		async primary_action(v) {
			if (!(v.price > 0)) {
				frappe.msgprint(__("Price must be greater than zero."));
				return;
			}
			d.get_primary_btn().prop("disabled", true);
			try {
				const args = { supplier: frm.doc.name, ...v };
				const method = "happy_kitchen.hk_operations.purchasing.add_supplier_product";
				let r = await frappe.xcall(method, args);
				if (r.exists) {
					const ok = await new Promise((resolve) => frappe.confirm(
						__("{0} already exists as {1}. Link it to {2} and add this price?",
							[frappe.utils.escape_html(r.exists.item_name), r.exists.item_code, frm.doc.name]),
						() => resolve(true), () => resolve(false)));
					if (!ok) return;
					r = await frappe.xcall(method, { ...args, link_existing: 1 });
				}
				d.hide();
				frappe.show_alert({ message: __("{0} added", [r.item_code]), indicator: "green" });
				hk_render_supplier_products(frm);
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		},
	});
	d.show();
}
