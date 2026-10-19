# Product labels on a Raspberry Pi label printer

When a Sales Order is **submitted**, the ERP adds its labels to a print queue. A Raspberry Pi next to the label printer checks the queue every 3 seconds, prints, and reports back. The Pi only makes outgoing connections to the ERP (hcl-erp.fbs-host.com until go-live, then erp.fbs-host.com), so nothing on the router or firewall needs to change.

Labels follow the printed Happy Concepts design (sample `label_sample_150x100.png` in the rebuild reference folder on the Mac), landscape on a 100 × 150 mm roll, turned a quarter turn by the ERP:
- product name;
- "Ingredients: …", heaviest first, built from the recipe;
- "This product contains … and their products.", from the ingredients' allergens;
- Net Weight and Storage;
- the manufacturer's name and address, and "Made in Hong Kong";
- the note ("For immediate consumption after opening") and the factory cross-contact statement;
- 此日期前最佳 (日/月/年) / Best Before (dd/mm/yyyy) with the date;
- the barcode from the item's Barcodes table (Code 39 shows `*…*`, as on the current labels).

A label prints automatically only after a manager has **checked** that product's label. If the recipe or an ingredient changes afterwards, labels wait again until someone re-checks it.

## 1. What to buy

| | Recommended | Notes |
|---|---|---|
| Printer | **Zebra ZD421d** (direct thermal, 203 dpi, USB) | The cheaper **ZD230d** also works. Both speak ZPL, which needs no driver on the Pi. Avoid "t" (thermal transfer) models unless labels must last for months. |
| Labels | Direct thermal, **100 × 150 mm**, 25 mm core | For chilled or frozen products, order **freezer-grade adhesive**. |
| Pi | Raspberry Pi 4 or 5 (2 GB is plenty), or a Pi Zero 2 W | Use Raspberry Pi OS Lite, with Wi-Fi or a cable. |

A non-Zebra printer also works, through CUPS. Set the printer's **Printer language** to *PNG (CUPS)* in the ERP (see the bottom of this guide).

## 2. In the ERP (once)

1. **Label Settings** (Recipes sidebar → Team & Clients) is already filled in from the current label: manufacturer and address, "Made in Hong Kong", the default note and the factory statement. Check them and change them there if needed.
2. **Label Printers → New**:
   - Name it e.g. `Kitchen Zebra`.
   - Leave *ZPL / 203 dpi / 100 × 150* as they are.
   - Save, then pick it as the **Default printer** in Label Settings.
3. **A user for the Pi.** You create this yourself, e.g. `label-printer@…`:
   - Give it **only** the role **Label Printer**. Remove the default roles.
   - On that user, go to **Settings → API Access → Generate Keys**, and keep the key and secret for step 3 below.
   - Back on the Label Printer, set **Raspberry Pi user** to this user.

## 3. On the Raspberry Pi

1. Flash Raspberry Pi OS Lite with Raspberry Pi Imager. Set Wi-Fi, a user and SSH in the Imager options.
2. Plug the Zebra into the Pi by USB and switch it on. Load the labels and run the printer's media calibration once; see its quick-start card.
3. Copy this folder (`happy_kitchen/label_agent/` in the app repository) to the Pi and install it:

   ```bash
   scp -r label_agent pi@<pi-address>:~
   ```
   ```bash
   ssh pi@<pi-address> 'cd label_agent && sudo bash install.sh'
   ```
4. Put the API key and secret in the settings file. Type them yourself:

   ```bash
   ssh -t pi@<pi-address> 'sudo nano /etc/hk-label-agent.conf'
   ```
5. Check the printer, then start the agent:

   ```bash
   ssh pi@<pi-address> 'sudo -u hk-label python3 /opt/hk-label-agent/hk_label_agent.py --selftest && sudo systemctl restart hk-label-agent'
   ```
6. In the ERP, open the Label Printer:
   - It should say **Online**.
   - Click **Print test label**.

## 4. Getting a product ready (once per product)

The report **Ingredient Label Check** (Recipes workspace → Reports) lists every bought-in ingredient used in a recipe with its label name and allergens, and what is still to do. Export it (Menu → Export) to use as a fill-in sheet.


1. **Each ingredient** (Item → **Label** tab):
   - **Name in ingredient lists**: what customers read, e.g. *Wheat flour*, not *Blue Ribbon Cake Flour*.
   - **Allergens**: use **Suggest allergens**, then check them against the supplier's pack.
   - Tick **Allergens reviewed**, even if there are none.
2. **Each product** (Item → **Label** tab):
   - Set **Storage**, **Net weight per piece** and **Pieces per label** (1 = every piece; 48 = one per carton of 48).
   - Set **Shelf Life In Days** on the Inventory tab.
   - For a barcode, add a row to the item's **Barcodes** table (Inventory tab): type CODE-39 for the current style, or EAN for a 13-digit retail barcode.
3. The Label tab shows the label exactly as it prints, plus a list of anything still missing. When the list is empty, read the whole label and click **Mark label as checked**.

## 5. Every day

- **Submit a Sales Order** and its labels print within seconds.
- The order shows a **Labels:** line, e.g. "3 printed" or "2 waiting for a label check".
- **Labels → Print labels** on the order prints again, or prints a different number of pieces.
- **Label Queue** in the sidebar lists every job. Open one to see its label, then use **Print again** or **Cancel**.
- Cancelling the order cancels any labels that haven't printed yet.

## Troubleshooting

| Problem | What to do |
|---|---|
| Printer shows **Offline** | Is the Pi on and connected? On the Pi, run `journalctl -u hk-label-agent -n 50`. |
| "Pi reports a problem: printer not found" | Check the USB cable and that the printer is switched on. `ls /dev/usb/` should show `lp0`. |
| A job is **Failed** | The error is on the job, e.g. out of labels or the head is open. Fix it, then use **Print again**. |
| A job is **Needs check** | Open the product and check its label (section 4). Waiting jobs print as soon as you do. |
| The print is offset or skips labels | Re-run the printer's media calibration. |
| Not a Zebra | Set up the printer in CUPS on the Pi (`sudo apt install cups`). In the settings file, empty `device` and set `cups_queue`. Set **Printer language** to *PNG (CUPS)* in the ERP. |
