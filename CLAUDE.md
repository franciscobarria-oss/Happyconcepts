# CLAUDE.md

Guidance for Claude Code working in this repository: the `happy_kitchen` Frappe app for Happy Concepts
(company "Happy Concepts", abbreviation HK, currency HKD), on ERPNext v16 + Frappe HR v16.

## Layout
- `happy_kitchen/hooks.py`: app hooks. Modules: Recipe Management, HK Operations (`modules.txt`).
- `happy_kitchen/setup/`: `install.py` (after_install), `blocks.py` (Custom HTML Blocks synced from `happy_kitchen/blocks/` on every migrate).
- `happy_kitchen/patches.txt`: `[pre_model_sync]` / `[post_model_sync]` patches. Every setup step must be idempotent.
- `tests/`: pure pytest tests, run on every PR by `.github/workflows/tests.yml`. Never import frappe there.
- `deploy/`: image build (`build_image.sh`, `versions.env`), environments in `deploy/README.md`.

## Rules
- Never hard-code the company name. Use `frappe.defaults.get_global_default("company")` (or a setting) and the company's `abbr` for "… - HK" names.
- Base setup lives in `setup/base_data.py` (plain data, tested) and `setup/base.py` (applies it, idempotent; run by after_install and the `base_setup` patch).
- Everything installs from code: DocTypes, custom fields (fixtures or patches), roles, workspaces, blocks (files), form scripts (`public/js` via `doctype_js`), print formats, settings defaults. No Client Scripts or hand-typed setup in the database.
- Labels in code are English; Chinese goes in `translations/zh-TW.csv`, generated from `translations/zh_tw_source.py`. Print formats and the Clock In kiosk stay bilingual.
- Pure maths lives in plain Python modules with unit tests; each feature also gets a rolled-back end-to-end test on the rebuild site.
- **Currency precision is 4** (prices are per gram); otherwise prices round to zero.
- **Never set `precision` on recipe quantity fields.** Frappe stores the rounded value, not just displays it; recipes use quantities like 0.025 egg (368 lines once had to be restored).
- Desk CSS/JS listed in `hooks.py` carry `?v=<_HK_ASSET_VERSION>`; bump it whenever one of those files changes, because /assets is cached long and these files aren't bundled.
- Workspace quick-list filters must use the object format (v16 bug with the list format).
- Use UTF-8 / utf8mb4 everywhere (Chinese item names).

## Server rules (learned the hard way)
- **Never put a folder inside `sites/<site>/private/backups/`.** Frappe's backup clean-up `os.remove`s every entry there and crashes on a directory, breaking the 6-hourly backups. One-off copies go in `private/hk_copies/<name>`.
- Copy a tarball to the server with `scp` first; don't pipe it into an ssh command that also runs `docker compose exec` (that command swallows stdin).
- From macOS, pack source with `COPYFILE_DISABLE=1 tar --no-xattrs`, or `._*` files get in and break `bench migrate` ("bad json").
- The site `encryption_key` (site_config.json) must go into full backups once email accounts or API keys exist. Never put it, passwords or API keys in the repo, chat or project files.
- The old production stack (`erpnext`, erp.fbs-host.com) owns nginx-proxy and Let's Encrypt. Other stacks only join its `erpnext_default` network from their frontend and use their own backend/websocket aliases. Don't edit the production compose file outside the go-live step.

## Purchasing (P4)
- Supplier fields `hk_min_order_amount`, `hk_products_tab`, `hk_products_html`; Item `hk_order_multiple` (patch `supplier_moq_fields`).
- MOQ rules are enforced on the server (`hk_operations/purchasing.py`, Purchase Order `validate` / `before_submit`), so API, Data Import and draft orders created by code obey them too. The form only adds an early warning.
- "+ Add Product" runs in the whitelisted `add_supplier_product` (one transaction: item and price together). Maths in `hk_operations/moq.py`.

## Recipes and costing (P6)
- DocType Recipe (named by its item) + Recipe Ingredient / Labour / Overhead / Step / Utensil / Packaging Group, and the single Recipe Settings. Types: Finished Product, Batch Preparation (stocked), Recipe Component (made fresh); sub-recipes pass cost per unit up. Status Active / Archived / Draft.
- Pure maths in `recipe_management/costing.py` (tests/test_costing.py) and `swap.py` (tests/test_swap.py); `pricing.py` reads Item Price, `usage.py` builds usage, `replace_ingredient.py` is the "Replace in recipes" API.
- Re-costing: nightly, on Item Price change (Recipe Settings `recost_on_price_change`) and on Item weight change; `last_costed_on` only moves when a cost changed.
- No data is loaded: the site starts empty and the team enters suppliers, products and recipes (decision 2026-10-17).

## Production (P9)
- Recipe Production Log (+ Item), naming RPL-.YYYY.-.####, submittable; only Active recipes can be logged.
- On submit (Recipe Settings `create_stock_entry_on_submit`): one draft Manufacture per Batch Preparation row (inputs from each item's default warehouse, output to the prep item's default warehouse at ingredient cost) and one draft Material Issue for the other rows. Whole-number UOMs round up.
- Page /app/kitchen-production calls `recipe_management/kitchen.py`; pure helpers in `recipe_management/production.py` (tests/test_production.py).

## End-to-end checks
- `happy_kitchen/e2e/<feature>.py` has `run()`: creates E2E-* records, asserts, always rolls back. Run with `bench --site hcl-erp.fbs-host.com execute happy_kitchen.e2e.<feature>.run`.

## Stock take (P10)
- Stock Take Sheet (+ items, up to 3 pack sizes from the Item's UOM conversions) and Stock Take (+ items): Draft → Submitted → Approved, or back to Draft with a rejection comment. Rules in `variance.check_transition` (tests/test_variance.py); the submitter can't approve, standard Submit is blocked.
- Approval posts a Stock Reconciliation (Recipe Settings `stock_take_sync_stock`); the company's first one is Opening Stock against the Temporary account.
- Count page /app/stock-take-count/<name>, printable sheet `count_print.sheet`, report Inventory Variance (tolerance `variance_tolerance_pct`).
- Item `hk_recipe` / `hk_recipe_qty` (patch `item_recipe_link_fields`) link a sales SKU to another item's recipe.
