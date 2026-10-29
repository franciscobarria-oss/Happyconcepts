"""End-to-end checks run on a real site and always rolled back:

	bench --site <site> execute happy_kitchen.e2e.<feature>.run

Each run() creates its own E2E-* records, asserts, prints "ok" and rolls everything back, so a
site keeps no trace of it (it is safe on the empty rebuild site; avoid production)."""

import frappe

# Safety net for live sites: nothing an e2e run does may be committed, whatever the code it calls does
# (several app functions commit by design). Importing any e2e module turns commit into a no-op for the
# process; every run() ends with a rollback. dates.py and labels.py restore it themselves and re-patch.
if getattr(frappe, "db", None) is not None:
	frappe.db.commit = lambda *a, **k: None
