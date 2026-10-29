frappe.listview_settings["Recipe"] = {
	add_fields: ["recipe_type", "status", "missing_price_count"],
	get_indicator(doc) {
		if (doc.status === "Archived") return [__("Archived"), "gray", "status,=,Archived"];
		if (doc.recipe_type === "Recipe Component")
			return [__("Recipe Component"), "purple", "recipe_type,=,Recipe Component"];
		if (doc.recipe_type === "Batch Preparation")
			return [__("Batch Preparation"), "orange", "recipe_type,=,Batch Preparation"];
		return [__("Finished Product"), "blue", "recipe_type,=,Finished Product"];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Finished Products"), () =>
			listview.filter_area.clear().then(() => listview.filter_area.add([["Recipe", "recipe_type", "=", "Finished Product"]]))
		);
		listview.page.add_inner_button(__("Batch Preparations"), () =>
			listview.filter_area.clear().then(() => listview.filter_area.add([["Recipe", "recipe_type", "=", "Batch Preparation"]]))
		);
		listview.page.add_inner_button(__("Recipe Components"), () =>
			listview.filter_area.clear().then(() => listview.filter_area.add([["Recipe", "recipe_type", "=", "Recipe Component"]]))
		);
	},
};
