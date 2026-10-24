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
- **SKUs:** our SKU is the Item code (ING-xxx for bought-in); a supplier's SKU is `supplier_part_no` on the Item's Supplier Items row. Item `hk_supplier_skus` (patch `supplier_sku_fields`, filled on Item validate by `sku_api.item_validate`, rules in `hk_operations/sku.py`, tests/test_sku.py) lists them and is in the Item `search_fields`, so any Item search finds an item by either. A supplier's SKU can belong to one item only. The Supplier Products tab, "+ Add Product" and Receive Delivery show/take the supplier SKU. e2e: `happy_kitchen.e2e.sku.run`.
- "+ Add Product" runs in the whitelisted `add_supplier_product` (one transaction: item and price together). Maths in `hk_operations/moq.py`.

## Recipes and costing (P6)
- DocType Recipe (named by its item) + Recipe Ingredient / Labour / Overhead / Step / Utensil / Packaging Group, and the single Recipe Settings. Types: Finished Product, Batch Preparation (stocked), Recipe Component (made fresh); sub-recipes pass cost per unit up. Status Active / Archived / Draft.
- Pure maths in `recipe_management/costing.py` (tests/test_costing.py) and `swap.py` (tests/test_swap.py); `pricing.py` reads Item Price, `usage.py` builds usage, `replace_ingredient.py` is the "Replace in recipes" API.
- Re-costing: nightly, on Item Price change (Recipe Settings `recost_on_price_change`) and on Item weight change; `last_costed_on` only moves when a cost changed.
- No data is loaded: the site starts empty and the team enters suppliers, products and recipes (decision 2026-10-17).

## Production (P9)
- Recipe Production Log (+ Item), naming RPL-.YYYY.-.####, submittable; only Active recipes can be logged.
- On submit (Recipe Settings `create_stock_entry_on_submit`): one draft Manufacture per Batch Preparation row (inputs from each item's default warehouse, output to the prep item's default warehouse at ingredient cost) and one draft Material Issue for the other rows. Whole-number UOMs round up.
- A Batch Preparation recipe keeps its Item's `valuation_rate` at the ingredient cost per unit, so ERPNext can value the prep before any of it is in stock.
- Page /app/kitchen-production calls `recipe_management/kitchen.py`; pure helpers in `recipe_management/production.py` (tests/test_production.py).

## End-to-end checks
- `happy_kitchen/e2e/<feature>.py` has `run()`: creates E2E-* records, asserts, always rolls back. Run with `bench --site hcl-erp.fbs-host.com execute happy_kitchen.e2e.<feature>.run`.

## Stock take (P10)
- Stock Take Sheet (+ items, up to 3 pack sizes from the Item's UOM conversions) and Stock Take (+ items): Draft → Submitted → Approved, or back to Draft with a rejection comment. Rules in `variance.check_transition` (tests/test_variance.py); the submitter can't approve, standard Submit is blocked.
- Approval posts a Stock Reconciliation (Recipe Settings `stock_take_sync_stock`); the company's first one is Opening Stock against the Temporary account.
  It is posted as Administrator (approver named in the remarks): approvers must not post reconciliations by hand, and ERPNext checks the session user's own Stock Reconciliation rights.
- **Blank counts are 0:** `submit_for_approval(name, zero_missing)` refuses a count with uncounted rows unless `zero_missing` is set; both the count page and the form first call `uncounted_items`, show the list ("will be set to 0") and ask to confirm. Confirmed rows get `counted` = 1, quantity 0 and `auto_zero` = 1, and a comment on the take lists them. Only rows on the take (the sheet's active items) are touched. Approval is unchanged.
- Count page /app/stock-take-count/<name>, printable sheet `count_print.sheet`, report Inventory Variance (tolerance `variance_tolerance_pct`).
- Item `hk_recipe` / `hk_recipe_qty` (patch `item_recipe_link_fields`) link a sales SKU to another item's recipe.

## Wastage and receiving (P11)
- Wastage Log (+ items, WST-.YYYY.-.####) issues stock on submit; if stock is short it still submits and sets `stock_note`. Wastage Reason has `reason_zh` (8 seeded by patch `wastage_receiving_setup`).
- Receive Delivery (/app/receive-delivery, button on submitted POs) → `kitchen.receive_po`: stock at the PO price, flags (pure `receiving.py`, tests/test_receiving.py) in Purchase Receipt `hk_has_discrepancy` / `hk_delivery_flags`, invoice price in PR Item `hk_invoice_rate` for the Price Variance report.
- Pure HK Operations rules (overtime, price %, food cost) live in `hk_operations/calc.py` (tests/test_hk_operations.py).

## Team (P12)
- Employee fields (patch `team_fields`): hk_short_name, hk_cert_expiry, pay fields at permlevel 1 (hk_monthly_base, hk_hourly_rate, hk_working_days, hk_hours_per_day, hk_hourly_cost, hk_default_overtime_rate, hk_pin_hash), readable by HR Manager / System Manager only.
- `hk_hourly_cost` is computed on the server (Employee validate, `hk_operations/team_api.py`) and synced to Activity Cost "Kitchen Labour". Maths and setup data in `hk_operations/team.py` (tests/test_team.py): MPF 5 % capped HK$1,500, PIN hash sha256("id:pin"), roster cycle, EO annual leave.
- Clock-in PINs are checked on the server (`team_api.clock_in`, 5 wrong tries lock 5 min); the kiosk never receives hashes or pay. Roster taps and "copy last week" run in `team_api.roster_cycle` / `roster_copy_week`.
- Blocks HK Team Today / HK Team Roster / HK Clock In are files in `blocks/`; workspaces Team and Clock In (module HK Operations), sidebars in `workspace_sidebar/`, icons in `desktop_icon/`. Starting data (departments, shifts, HK Statutory 2026-27 holidays, Annual Leave, overtime rates, activity types) from patch `team_setup`. No employees are loaded.
- Payroll stays with the outside provider: Overtime Entry (submit = approve) and the Overtime Summary report.

## Theme and language (P13)
- Desk theme `public/css/hk_theme.css` applies only under `html.hk-theme`, which `public/js/hk_theme.js` sets from `frappe.boot.hk_theme` (`theme.boot_session`). On when Recipe Settings `desk_theme` is ticked (patch `theme_defaults` ticks it once per site); site_config `hk_theme` 1/0 overrides. Pure rules in `theme_rules.py` (tests/test_theme.py).
- EN / 中 toggle: page header on desktop, bottom of the side menu under 768 px; calls `theme.set_language` (en / zh-TW only). hk_theme.js also runs sidebar labels and workspace text blocks through `__()`.
- Translations: edit `translations/zh_tw_source.py`, then `python3 happy_kitchen/translations/zh_tw_source.py` writes zh-TW.csv. `python3 happy_kitchen/translations/strings.py` lists strings still missing (DocType/report/page/workspace JSON, patch custom fields, `__()` / `_()`); tests/test_translations.py fails until each is in `ZH_TW` or `LEAVE_AS_IS`. Generic ERPNext words (Rate, Batch, Pending, Rejected, Status, Supplier...) go in `LEAVE_AS_IS`, never in `ZH_TW`, because app translations override ERPNext's everywhere.

## Today home (P14)
- Desktop icon Today → workspace Today (module Recipe Management) with one block, HK Today (`blocks/today.*`). It calls `today.today()`, which merges `dashboard.kitchen_today()` (KPIs with breakdowns, orders by day Late/Today/Tomorrow/Day after, waiting on you) and `today_board.today_board()` (happening today, ordering/receiving/production tasks) with the pure `board.merge_today` (tests/test_board.py). Each part is gated by read permission. Simple/Detailed is remembered per device (localStorage `hk_today_view`); the block refreshes every 5 minutes.
- Ordering looks 3 days ahead (`board.first_need`, `board.to_order`: short minus what is on open or draft POs, rounded up to the item's min order qty and `hk_order_multiple`). "Create draft order" → `today_board.create_purchase_order` (a draft only).
- Label status on orders and the label tasks (labels to check, failed prints) come from Label Job (P15).
- A4 production sheet: `/api/method/happy_kitchen.recipe_management.production_sheet.sheet?date=YYYY-MM-DD` (template `templates/production_sheet.html`, maths in `daily_plan.plan_day`, tests/test_daily_plan.py).
- Print format HK Delivery Note (bilingual, module HK Operations). Customer delivery times, invoice no. and line notes are not added: the review left them undecided (01 review 9.5 / 14.8).
- "Week ahead" card on Today (`today_board.week_ahead`, pure `board.week_load`, tests/test_board.py): per day for the next 7 days, orders going out (late ones count today) plus deliveries coming in; a day is Busy from 75 % of the week's peak (peak of at least 3), Quiet up to 25 %.
- Workspace Recipes (desktop icon label "Recipes"): shortcuts, Active-recipe quick lists per type (object-format filters) and link cards.

## Labels (P15)
- DocTypes (module HK Operations): Allergen (+ Item Allergen), Label Job (LBL-.YYYY.-.#####), Label Printer, Label Settings, OEM Spec Sheet. Item Label tab fields from patch `labels_setup` (also seeds the HK Cap. 132W allergens + sesame and the Label Printer role); label wording and maker lines from `label_design_defaults` (fills blanks only).
- Sales Order submit → one Label Job per line (`labels.on_sales_order_submit`, Label Settings `create_on_submit`): Queued only when the product's label is checked and its content fingerprint is unchanged, else Needs check; cancelling the order cancels unprinted jobs. "Mark label as checked" (manager roles) releases waiting jobs.
- Content (`labels.label_content`): ingredients from the recipe with sub-recipes broken down and packaging dropped, heaviest first; allergen union; an approved OEM Spec Sheet overrides shelf life and storage per customer. Pure maths in `hk_operations/label_data.py`, drawing (Pillow, 100×150 Happy Concepts layout, ZPL and PNG) in `label_render.py`; tests/test_labels.py (CI installs pillow).
- Raspberry Pi agent in `label_agent/` (README.md = setup guide): polls `labels.agent_poll` / reports `labels.agent_done` as a user with only the Label Printer role. agent_poll commits by design. The Pi user, its API key and secret are created by hand on the site and typed on the Pi; never in code, chat or project files.
- Ingredient Label Check report = the fill-in sheet of label names and allergens for every bought-in ingredient used in a recipe.

## Dates and batches (P15b)
- Item fields (patch `date_tracking_setup`): `hk_open_life_value` / `hk_open_life_unit` (Days / Hours), `hk_open_storage`, `hk_item_name_zh`. The patch also adds the Chiller warehouse (company abbr, via `base.warehouses`). Pure date maths in `hk_operations/dates.py` (hours count from the minute; days count the opening day as day 1 and end 23:59; lot `L<yymmdd>`, `-2` for a second run), label text in `date_labels.py`, drawing in `label_render.render_kitchen` (tests/test_dates.py).
- **No item flags are changed by the app.** `has_batch_no` / `has_expiry_date` are never set (stock takes need a batch per row on batch items). On Recipe Production Log submit every Batch Preparation / Finished Product row gets `lot_no` and `use_by` (item shelf life); an ERPNext Batch is created and set on the Manufacture output row only when the item already has `has_batch_no`. The patch turns on Stock Settings `enable_serial_and_batch_no_for_item` (off by default on v16, it blocks `has_batch_no` on items).
- DocType Opened Item (OPN-.YYYY.-.#####): Open / Used up / Discarded. Screen /app/kitchen-opened (`dates_api.find_item`, `open_item`); "Print batch labels" button on the log (`dates_api.print_batch_labels`); batch labels are queued on submit when Label Settings `batch_labels_on_submit` is on.
- Label Job `kind` Product / Opened / Batch; Label Printer `label_use` (Kitchen date labels default to 50×30 mm); Label Settings `date_label_printer`. Kitchen jobs store `{"lines": ...}` in `label_json`, the agent draws them with `render_kitchen`. ZPL only (SATO with ZPL emulation); no SBPL. Product labels show the lot (the production run's lot that day, else `L<yymmdd>`).
- Today shows a "Use by" card (`dates_api.expiring`): Discarded → `kitchen.log_wastage` with reason "Spoiled / Expired"; Used up just closes.
- e2e: `happy_kitchen.e2e.dates.run`.

## Gmail orders (foundation)
- DocTypes (module HK Operations): Gmail Settings (single; client id / secret / refresh token are Password fields entered by hand, never in code, chat or project files), Email Order (MAIL-.YYYY.-.#####, unique `message_id`) + Email Order Line. `hk_operations/gmail_orders.py` is the only code that talks to Google (scope `gmail.readonly` only: never sends, labels or deletes); pure reading rules (sender allow-list, body text, order lines) in `hk_operations/email_orders.py` (tests/test_email_orders.py).
- `scheduled_fetch` (cron every 15 min) does nothing until Gmail Settings `enabled` is ticked and complete. Reads only mail under the Gmail label from the last `look_back_days`; one Email Order per message id (never twice); senders outside `allowed_senders` are recorded as Ignored.
- Each readable email makes a **draft** Sales Order (never submitted). Customer matched by email (Customer.email_id or Contact) else created with a Contact. Products: internal SKU = Item code `SKU-nnnn` (`sku.next_code`), external SKU = the customer's code on the Item's Customer Items (`Item Customer Detail.ref_code`); a known (customer, external SKU) or product name reuses the item. Item `hk_supplier_skus` (label "External SKUs") holds supplier and customer codes for the Item search. Unreadable lines go to `unparsed` and the order is Needs review.
- Google steps Francisco does by hand: `deploy/gmail_orders.md`; the one-time sign-in is `deploy/gmail_authorize.py` (run on his own computer). Do not connect to his real mailbox until he says the steps are done in the thread. e2e with fake messages: `happy_kitchen.e2e.email_orders.run`.

## Revise order
- A follow-up email in the same Gmail thread, from the same sender, as an earlier Email Order **amends that order** (`gmail_orders.find_prior` / `revise`) instead of making a second one: the new lines replace the old ones (an email is read without its quoted reply text, `email_orders.strip_quoted`). A draft Sales Order is changed; a submitted one is not touched, only flagged with the proposal (Order Revision `applied` = 0). An email that changes nothing is Ignored.
- Staff edits count too: Sales Order `validate` / `before_update_after_submit` (`revisions_api.track`) keeps every change to items or quantities when the order came from an email or is submitted. Each is an Order Revision (REV-.YYYY.-.#####: items before and after, summary, who, when; pure rules in `hk_operations/revisions.py`, tests/test_revisions.py).
- Sales Order fields (patch `revise_order_fields`): `hk_email_order`, `hk_revision_count`, `hk_needs_review` ("Revised: check before delivering", allow on submit). The flag shows on the form with "Mark revision as checked" (Sales Manager / System Manager, `revisions_api.mark_checked`), "Revision history" and a Today "Waiting on you" line. e2e: the revise section of `happy_kitchen.e2e.email_orders.run`.
- **Encryption key:** `bench new-site` on v16 does not write `encryption_key`; Frappe makes one on the first Password save, and two workers doing that at once end with a key that can't read the secret (happened on hcl-erp, 2026-10-20). Patch `encryption_key_setup` (also run after migrate) creates it up front. The key lives in site_config.json and goes in the backups, never the repo.
- **PDF orders:** `_take` also reads PDF attachments (Gmail `attachments.get`, still `gmail.readonly`): each PDF is kept as a private File on the Email Order, and its text is added to the body under "--- Attachment: name ---". `pdf_text` uses pdfplumber tables first (`email_orders.table_to_lines`: header row with a quantity column and a code or description column becomes "CODE | Description | Qty" lines), else the page text (pypdf). Scans are not read (no OCR). "Read again" on an Email Order (`gmail_orders.reprocess`, Sales Manager / System Manager, only without a Sales Order) re-reads the email and PDFs after the rules change. Three real PO layouts are read: ruled tables (`table_to_lines`, merged multi-item rows are split, header words Qty/Quantity + Description/Product Code), and positioned text with a Description + Quantity header (`text_item_lines`: description, item no., qty, unit, price, amount; wrapped descriptions joined). Up to 8 PDFs per email. Free-text bodies and image-only (PNG) orders are not read.
- **One order per PO:** `pdf_text` writes `--- PO <no> | <delivery date> ---` markers (`email_orders.text_item_pages`, `po_number`, `delivery_date_of`, `parse_date`); `parse_lines` gives each line `po_no` / `delivery_date`. `gmail_orders.process` makes one draft Sales Order per PO number (`_make_sales_order`: `po_no`, item delivery dates when today or later, else the lead-time fallback). A PO that already has a sales order for that customer is skipped and noted; an email whose POs all exist is Ignored. Email Order Line carries `po_no`, `delivery_date`, `sales_order`. A thread follow-up revises the prior order only when its lines have no PO number.
- **Today:** `dashboard.kitchen_today` puts "Emails to read by hand" (Email Order Needs review/Failed without a sales order) and "Draft orders from email to check" (draft Sales Orders with `hk_email_order`) first in "Waiting on you"; routes may carry JSON filters (`field=["is","set"]`, parsed in `blocks/today.js`); Simple view shows 4 lines.
- **Extra senders:** Gmail Settings `extra_senders` (patch `gmail_extra_senders` fills a blank with plaza-network.com): the search becomes `(label:"Orders" OR from:domain ...) newer_than:Nd` (`email_orders.search_query`, tests/test_email_orders.py), because the app has read-only Gmail access and cannot label mail itself.
- **Email orders card (Today):** `hk_operations/email_card.card()` (pure rules `email_card_rules.py`, tests/test_email_card.py) feeds `data.email` in `today.today()`: emails to read by hand (and how many have a PDF), draft orders from email by delivery day, pick-up health (last check, error, label, extra senders), "Pick up orders now" (System Manager, `gmail_orders.fetch_now`). tests/test_blocks_syntax.py runs `node --check` on every `blocks/*.js`: today.js had a duplicate `const dl` (a SyntaxError) from P15b on, found 2026-10-24.
- **Review screen:** Email Order form shows "Review" (HTML field `review_html`, rendered by `public/js/email_order.js` from `gmail_orders.review_data`): email text and PDF viewers on the left, what the system read on the right (reasons from the pure `email_orders.review_reasons`, lines with PO / delivery date / item / sales order, items not matched highlighted, unparsed lines, error). Buttons for Needs review / Failed: "Read again", "Mark as entered by hand" (`mark_done_by_hand`, status **Done by hand**, optional Sales Order link) and "Not an order" (`mark_not_order`, status Ignored); both leave the Today count. Sales Manager / System Manager only.
