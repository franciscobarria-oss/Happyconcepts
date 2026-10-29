# One-off data loads for hcl-erp

These scripts loaded master data into hcl-erp. They are kept here so the work can be repeated or checked.
They are not part of the app and never run on install or migrate.

Every script is idempotent and has a dry run that rolls back. The usual way to run one:

1. Take a backup of the site first (into `private/hk_copies/<name>`, never into `private/backups/`).
2. Copy the script and its input file into the backend container's `/tmp`.
3. `bench --site hcl-erp.fbs-host.com console`, then
   `g = globals(); exec(open("/tmp/<script>.py").read(), g); g["run"](..., dry_run=True)`.
4. Check the counts and review files, then run again with `dry_run=False`.

The input files (workbook extracts, Xero exports, staging recipe dumps, code maps) hold business data and stay
out of the repo. They live on Francisco's Mac under `~/Documents/hcl-erp-import/`.

| Folder | Loaded | What |
| --- | --- | --- |
| `purchases/` | 2026-10-22 to 10-24 | Suppliers, ingredients and buying prices from the Jun-Sep 2026 purchase workbooks (`import_purchases.py`), new items and supplier links from the old site (`create_new_items.py`, `link_suppliers.py`), duplicate merges (`dupe_report.py`, `merge_dupes.py`), and the "current" marking of repeated items (`mark_current.py`, `current_flag.py`, `tag_current.py`). `import_sales_employees.py` copies sales products and employees from an old-site export. |
| `xero/` | 2026-10-23 | Xero customers from the Contacts export (`import_xero_customers.py`), Xero invoices as draft Sales Orders (`import_xero_orders.py`, `create_halloween_items_and_orders.py`), and closing past ones (`complete_xero_orders.py`). |
| `recipes/` | 2026-10-27 to 10-28 | 68 of the 75 staging recipes. See `recipes/README.md`. |

`purchases/current_flag.py` made the Item field "Current" (`is_current`) by hand on the live site. The app version
of that field is PR #20 (`hk_is_current`, "Current Purchase"). Its patch moves the ticks over and removes the hand-made field. It is not deployed yet.
