# Gmail order pick-up: the steps you do by hand

The site reads order emails from **one Gmail label**, read-only, and makes a **draft** Sales Order
from each. It never sends, labels or deletes mail. Nothing is read until you switch it on.

## 1. Gmail
1. In the Gmail account that receives orders, create a label called **Orders** (or any name; match it in step 4).
2. Make a filter (Settings > Filters) that applies the label to order emails (from your customers, or by subject), or apply it by hand.

## 2. Google Cloud (one time, free)
1. Go to https://console.cloud.google.com and create a project (e.g. "Happy Kitchen").
2. APIs & Services > Library > **Gmail API** > Enable.
3. APIs & Services > OAuth consent screen: User type **External**, fill the app name and your email.
   Add the scope `.../auth/gmail.readonly`. Add your Gmail address as a **test user**.
4. **Publish the app** (OAuth consent screen > "Publish app" / In production). While it is left in
   "Testing", Google expires the token after 7 days. An unpublished-verification warning at sign-in is
   normal for your own app: Advanced > Go to Happy Kitchen.
5. APIs & Services > Credentials > Create credentials > OAuth client ID > Application type **Desktop app**.
   Copy the **client ID** and **client secret**.

## 3. Sign in once, on your own computer
```
python3 deploy/gmail_authorize.py
```
Type the client ID, the secret (hidden), sign in with the Gmail account, and approve "View your email messages".
The script prints a **refresh token** in the terminal only. Check it says the granted scope is
`.../auth/gmail.readonly`.

## 4. The site
Open **Gmail Settings** on https://hcl-erp.fbs-host.com and fill in:
- Google client ID, Google client secret, Google refresh token (stored encrypted)
- Gmail label (default Orders)
- Only these senders (optional; addresses or @domains; blank = anyone with the label)
- Save, press **Check connection** (it shows the mailbox it reached), then tick **Pick up orders from Gmail**.

Tell Claude in the thread when step 4 is done. Until then the site makes no connection to Google.

## What it does
- Every 15 minutes (or **Pick up orders now**) it lists mail under the label from the last 14 days.
- Each email becomes an **Email Order** keyed by its Gmail message id, so it is never picked up twice.
- Order lines are read from tables (`CODE | Product | Qty`) and lines like `12 x Brownie`, `Brownie x 12`,
  `5 x [CK-001] Cookie`. Anything else is listed under "Lines that could not be read" and the order is marked Needs review.
- The sender becomes a Customer (matched by email when it exists) and each product becomes an Item:
  **internal SKU** = the Item code (`SKU-0001`, `SKU-0002`...), **external SKU** = the customer's code,
  stored on the Item's Customer Items table. A known external SKU (for that customer) or product name reuses the item.
- A draft Sales Order is created; check quantities, prices and the delivery date, then submit it yourself.

To stop: untick the switch in Gmail Settings, or remove the app's access at https://myaccount.google.com/permissions.
