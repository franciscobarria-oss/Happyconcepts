app_name = "happy_kitchen"
app_title = "Happy Kitchen"
app_publisher = "Happy Concepts"
app_description = "Recipes, costing, kitchen screens, stock take, team and labels for Happy Concepts"
app_email = "francisco.barria@gmail.com"
app_license = "mit"

required_apps = ["erpnext", "hrms"]

after_install = "happy_kitchen.setup.install.after_install"
# Custom HTML Blocks are kept as files in happy_kitchen/blocks/ and upserted on every migrate.
after_migrate = ["happy_kitchen.setup.blocks.sync", "happy_kitchen.patches.encryption_key_setup.ensure_key"]

# Desk-wide CSS/JS. /assets is served with a long cache lifetime and these files are not
# bundled, so each URL carries ?v=<_HK_ASSET_VERSION>.
# Bump _HK_ASSET_VERSION whenever any file listed in app_include_css / app_include_js changes.
_HK_ASSET_VERSION = "0.3.0"
# Happy Concepts desk theme: always loaded, only active under html.hk-theme, which
# hk_theme.js sets from boot (Recipe Settings > "Happy Concepts desk theme", see theme.py).
_APP_CSS = ["css/hk_theme.css"]
_APP_JS = [
	"js/hk_theme.js",  # theme switch, EN / 中 toggle, sidebar and workspace text through __()
	"js/hk_replace_ingredient.js",  # "Replace in recipes" dialog, used by the Recipe and Item forms
]


def _asset(path):
	return f"/assets/happy_kitchen/{path}?v={_HK_ASSET_VERSION}"


app_include_css = [_asset(p) for p in _APP_CSS]
app_include_js = [_asset(p) for p in _APP_JS]

boot_session = "happy_kitchen.theme.boot_session"

# Form scripts live in public/js and are attached here (no Client Scripts in the database).
doctype_js = {
	"Supplier": "public/js/supplier.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Item": "public/js/item.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Employee": "public/js/employee.js",
	"Sales Order": "public/js/sales_order.js",
	"Gmail Settings": "public/js/gmail_settings.js",
	"Email Order": "public/js/email_order.js",
}

jinja = {
	"methods": ["happy_kitchen.recipe_management.utils.get_recipe_branding"],
}

doc_events = {
	"Item": {
		"validate": [
			"happy_kitchen.hk_operations.sku_api.item_validate",
			"happy_kitchen.hk_operations.current_flag_api.item_validate",
		],
		"on_update": "happy_kitchen.recipe_management.doctype.recipe.recipe.recost_recipes_for_item_weight",
	},
	"Item Price": {
		"on_update": "happy_kitchen.recipe_management.doctype.recipe.recipe.recost_recipes_for_item",
	},
	"Employee": {
		"validate": "happy_kitchen.hk_operations.team_api.employee_validate",
		"on_update": "happy_kitchen.hk_operations.team_api.employee_on_update",
	},
	"Sales Order": {
		# one Label Job per line (see hk_operations/labels.py)
		"on_submit": "happy_kitchen.hk_operations.labels.on_sales_order_submit",
		"on_cancel": "happy_kitchen.hk_operations.labels.on_sales_order_cancel",
		# a change to the items after the order came from an email, or after it was submitted, is kept in Order Revision
		"validate": "happy_kitchen.hk_operations.revisions_api.track",
		"before_update_after_submit": "happy_kitchen.hk_operations.revisions_api.track",
	},
	"Purchase Order": {
		"validate": "happy_kitchen.hk_operations.purchasing.validate_purchase_order",
		"before_submit": "happy_kitchen.hk_operations.purchasing.before_submit_purchase_order",
	},
}

scheduler_events = {
	"daily": ["happy_kitchen.recipe_management.doctype.recipe.recipe.recost_recipes"],
	"cron": {"*/15 * * * *": ["happy_kitchen.hk_operations.gmail_orders.scheduled_fetch"]},
}
