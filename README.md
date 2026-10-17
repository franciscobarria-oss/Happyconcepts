# Happy Kitchen

Custom Frappe app for Happy Concepts' central kitchen, on ERPNext v16 + Frappe HR v16:
recipes and costing, production, stock take, wastage, receiving, team and clock-in, product labels.

Install on a bench that already has erpnext and hrms:

    bench get-app happy_kitchen https://github.com/franciscobarria-oss/happyconcepts
    bench --site <site> install-app happy_kitchen

Run the unit tests (no site needed): `pip install pytest python-barcode==0.16.1 && pytest -q`.
See CLAUDE.md for the working rules.
