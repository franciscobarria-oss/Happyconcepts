import frappe, json
g=globals()
exec(open("/tmp/import_xero_orders.py").read(), g)
def mk(dry):
    for code,name in [("798816166","Grab & Go - Halloween Chocolate Cookie"),("798816167","Grab & Go - Halloween Pistachio Cookie"),("798816168","Grab & Go - Halloween Chocolate Brownies")]:
        if not frappe.db.exists("Item",code):
            frappe.get_doc({"doctype":"Item","item_code":code,"item_name":name,"item_group":"Products","stock_uom":"Nos","is_sales_item":1,"is_purchase_item":0,"is_stock_item":1}).insert(ignore_permissions=True)
    R=g["run"]("/tmp/xero_orders.json", dry_run=dry)
    return R
R=mk(DRY)
print("HRES", DRY, len(R["created"]), len(R["missing_items"]), R["errors"][:3])
