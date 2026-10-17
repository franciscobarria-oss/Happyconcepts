app_name = "happy_kitchen"
app_title = "Happy Kitchen"
app_publisher = "Happy Concepts"
app_description = "Recipes, costing, kitchen screens, stock take, team and labels for Happy Concepts"
app_email = "francisco.barria@gmail.com"
app_license = "mit"

required_apps = ["erpnext", "hrms"]

after_install = "happy_kitchen.setup.install.after_install"
# Custom HTML Blocks are kept as files in happy_kitchen/blocks/ and upserted on every migrate.
after_migrate = ["happy_kitchen.setup.blocks.sync"]

# Desk-wide CSS/JS. /assets is served with a long cache lifetime and these files are not
# bundled, so each URL carries ?v=<_HK_ASSET_VERSION>.
# Bump _HK_ASSET_VERSION whenever any file listed in app_include_css / app_include_js changes.
_HK_ASSET_VERSION = "0.1.0"
_APP_CSS = []  # e.g. "css/hk_theme.css"
_APP_JS = []  # e.g. "js/hk_theme.js"


def _asset(path):
	return f"/assets/happy_kitchen/{path}?v={_HK_ASSET_VERSION}"


app_include_css = [_asset(p) for p in _APP_CSS]
app_include_js = [_asset(p) for p in _APP_JS]

# Form scripts live in public/js and are attached here (no Client Scripts in the database).
doctype_js = {}

doc_events = {}

scheduler_events = {}
