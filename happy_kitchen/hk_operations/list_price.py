"""Supplier and buying price shown as columns on the Item list (pure rules, tests/test_list_price.py)."""


def pick(prices, default_suppliers=()):
	"""The price to show: one from the item's first listed supplier if it has one, else the newest.
	prices: dicts with supplier, rate, uom, currency, valid_from (date or text), modified."""
	prices = [p for p in prices if p.get("rate") is not None]
	if not prices:
		return None
	for s in default_suppliers:
		mine = [p for p in prices if p.get("supplier") == s]
		if mine:
			return max(mine, key=_age)
	return max(prices, key=_age)


def _age(p):
	return (str(p.get("valid_from") or ""), str(p.get("modified") or ""))


def price_text(price):
	"""'HKD 418 / Tub'; trailing zeros dropped, up to 4 decimals (prices can be per gram)."""
	if not price:
		return ""
	rate = ("%.4f" % float(price["rate"])).rstrip("0").rstrip(".")
	text = f"{price.get('currency') or ''} {rate}".strip()
	return f"{text} / {price['uom']}" if price.get("uom") else text
