"""Draw a product label as a black-and-white picture and turn it into printer data.

The label is drawn once, on the server, with Pillow. The same picture is shown as
the preview in the ERP and sent to the printer, either as ZPL (Zebra and most
thermal label printers) or as a PNG for printers driven through CUPS. Pure
functions, unit-tested in tests/test_labels.py.

Layout (landscape, as on the Happy Concepts labels):

	Product name (bold)
	Ingredients: ...
	This product contains ... and their products.   | For immediate consumption after opening
	Net Weight : 80g                                | Produced in a factory where ...
	Storage : Store in a cool dry place             |
	Manufacturers:                                  |      此日期前最佳 (日/月/年)
	Happy Concepts Food Ltd. / address              |     Best Before (dd/mm/yyyy)
	Made in Hong Kong                               |            07/10/2026
	                     ||||||||||||||||||||
	                        *798816138*
"""

from __future__ import annotations

import base64
import io
import os
import re

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
CJK_DIR = "/usr/share/fonts/opentype/noto"
# First file found wins; the ERP image only has the plain and bold DejaVu Sans.
FONTS = {
	"regular": ["DejaVuSans.ttf"],
	"bold": ["DejaVuSans-Bold.ttf"],
}
CJK_FONTS = {"regular": "NotoSansCJK-Regular.ttc", "bold": "NotoSansCJK-Bold.ttc"}
_CJK = re.compile(r"[⺀-鿿豈-﫿＀-￯]")
_cjk_index: dict[str, int] = {}

BEST_BEFORE_ZH = "此日期前最佳 (日/月/年)"
BEST_BEFORE_EN = "Best Before (dd/mm/yyyy)"


def _cjk_font(kind: str, size: int):
	"""Noto Sans CJK, Traditional Chinese face (the .ttc holds JP/KR/SC/TC/HK)."""
	path = os.path.join(os.environ.get("HK_LABEL_CJK_DIR", CJK_DIR), CJK_FONTS[kind])
	if path not in _cjk_index:
		_cjk_index[path] = -1
		for i in range(10):
			try:
				name = " ".join(ImageFont.truetype(path, 12, index=i).getname())
			except OSError:
				break
			if " TC" in name:
				_cjk_index[path] = i
				break
	if _cjk_index[path] < 0:
		return None
	return ImageFont.truetype(path, size, index=_cjk_index[path])


def _font(kind: str, px: float, text: str = ""):
	size = max(6, int(px))
	if text and _CJK.search(text):
		f = _cjk_font(kind, size)
		if f:
			return f
	folder = os.environ.get("HK_LABEL_FONT_DIR", FONT_DIR)
	for name in FONTS[kind]:
		try:
			return ImageFont.truetype(os.path.join(folder, name), size)
		except OSError:
			continue
	return ImageFont.load_default(size)


def _wrap(draw, text: str, font, width: int) -> list[str]:
	lines: list[str] = []
	for para in (text or "").split("\n"):
		line = ""
		for word in para.split():
			trial = f"{line} {word}".strip()
			if draw.textlength(trial, font=font) <= width or not line:
				line = trial
			else:
				lines.append(line)
				line = word
		lines.append(line)
	return lines


def barcode_modules(kind: str, value: str) -> tuple[str, str]:
	"""Bars as a string of 1 (black) / 0 (white) modules, and the text printed
	under them. kind: CODE-39, EAN (13 digits), EAN-8, UPC-A; anything else is Code 128."""
	from barcode import EAN8, EAN13, UPCA, Code39, Code128

	kind = (kind or "").upper().replace("_", "-")
	value = (value or "").strip()
	if kind in ("CODE-39", "CODE39"):
		b = Code39(value, add_checksum=False)
		return b.build()[0], f"*{b.get_fullcode()}*"
	if kind in ("EAN", "EAN-13", "EAN13", "JAN", "GTIN") and len(value) in (12, 13) and value.isdigit():
		b = EAN13(value[:12])
		return b.build()[0], b.get_fullcode()
	if kind in ("EAN-8", "EAN8") and len(value) in (7, 8) and value.isdigit():
		b = EAN8(value[:7])
		return b.build()[0], b.get_fullcode()
	if kind in ("UPC-A", "UPC", "UPCA") and len(value) in (11, 12) and value.isdigit():
		b = UPCA(value[:11])
		return b.build()[0], b.get_fullcode()
	b = Code128(value)
	return b.build()[0], value


def render(label: dict, width_mm: float = 150, height_mm: float = 100, dpi: int = 203) -> Image.Image:
	"""One label as a 1-bit landscape image (the longer side across), whatever the
	roll's orientation; for_printer() turns it for portrait rolls. `label` keys:
	title, ingredients, contains, net, storage, maker (list), origin, note,
	factory, best_before, lot, barcode ({"type", "value"} or None), banner."""
	W = round(max(width_mm, height_mm) / 25.4 * dpi)
	H = round(min(width_mm, height_mm) / 25.4 * dpi)
	u = H / 595.0  # sizes below are taken from the 842 x 595 scan of the printed label
	img = Image.new("1", (W, H), 1)
	d = ImageDraw.Draw(img)
	mx, top, bottom = round(0.045 * W), round(0.07 * H), round(0.035 * H)
	left_w = round(0.5 * W) - mx - round(10 * u)
	rx = round(0.545 * W)
	right_w = W - mx - rx

	# barcode block at the bottom
	bars, bar_text = None, ""
	if label.get("barcode") and label["barcode"].get("value"):
		try:
			bars, bar_text = barcode_modules(label["barcode"].get("type"), label["barcode"]["value"])
		except Exception:  # an invalid barcode is reported by the label check; draw the rest
			bars = None
	bar_h, bar_txt_px = round(95 * u), 20 * u
	bottom_block = (bar_h + round(bar_txt_px * 1.3) + round(14 * u)) if bars else 0
	y_max = H - bottom - bottom_block

	def plan(body_px: float, title_px: float):
		"""Text lines per block at these sizes, and where the columns end."""
		body = _font("regular", body_px)
		lh = round(body_px * 1.45)
		tfont = _font("bold", title_px, label.get("title") or "")
		title = _wrap(d, label.get("title") or "", tfont, W - 2 * mx)
		ing = _wrap(d, "Ingredients: " + label["ingredients"], body, W - 2 * mx) if label.get("ingredients") else []
		y_cols = top + len(title) * round(title_px * 1.3) + round(title_px * 0.7) + len(ing) * lh + round(lh * 0.9)
		left = []
		for key in ("contains", "net", "storage"):
			if label.get(key):
				left += _wrap(d, label[key], body, left_w)
		left_gap = 1 if label.get("maker") else 0
		maker = []
		if label.get("maker"):
			maker = ["Manufacturers:"]
			for line in label["maker"]:
				maker += _wrap(d, line, body, left_w)
		origin = _wrap(d, label["origin"], body, left_w) if label.get("origin") else []
		left_end = y_cols + (len(left) + left_gap + len(maker) + (1 if origin else 0) + len(origin)) * lh
		right = []
		for key in ("note", "factory"):
			if label.get(key):
				right += _wrap(d, label[key], body, right_w)
		date_h = round(23 * u * 1.35) * (4 if label.get("lot") else 3) if label.get("best_before") else 0
		right_end = y_cols + len(right) * lh + (round(lh * 0.9) if right and date_h else 0) + date_h
		return {"body": body, "lh": lh, "tfont": tfont, "title": title, "title_lh": round(title_px * 1.3),
		        "title_px": title_px, "ing": ing, "y_cols": y_cols, "left": left, "left_gap": left_gap,
		        "maker": maker, "origin": origin, "right": right, "fits": max(left_end, right_end) <= y_max}

	body_px, title_px = 15.5 * u, 22 * u
	p = plan(body_px, title_px)
	while not p["fits"] and body_px > 8 * u:
		body_px -= 0.5 * u
		title_px = max(16 * u, title_px - 0.5 * u)
		p = plan(body_px, title_px)

	# title and ingredients across the full width
	y = top
	for line in p["title"]:
		d.text((mx, y), line, font=p["tfont"], fill=0)
		y += p["title_lh"]
	y += round(p["title_px"] * 0.7)
	for line in p["ing"]:
		d.text((mx, y), line, font=_font("regular", body_px, line), fill=0)
		y += p["lh"]

	# left column
	lh, y = p["lh"], p["y_cols"]
	for line in p["left"]:
		d.text((mx, y), line, font=_font("regular", body_px, line), fill=0)
		y += lh
	y += p["left_gap"] * lh
	for line in p["maker"]:
		d.text((mx, y), line, font=_font("regular", body_px, line), fill=0)
		y += lh
	if p["origin"]:
		y += lh
		for line in p["origin"]:
			d.text((mx, y), line, font=p["body"], fill=0)
			y += lh

	# right column: notes, then the best-before block centred under them
	y = p["y_cols"]
	for line in p["right"]:
		d.text((rx, y), line, font=_font("regular", body_px, line), fill=0)
		y += lh
	if label.get("best_before"):
		if p["right"]:
			y += round(lh * 0.9)
		block_lh = round(23 * u * 1.35)
		cx = rx + right_w / 2
		block = [(BEST_BEFORE_ZH, "regular"), (BEST_BEFORE_EN, "bold"), (label["best_before"], "bold")]
		if label.get("lot"):
			block.append((f"Lot 批號 {label['lot']}", "regular"))
		for text, kind in block:
			f = _font(kind, 23 * u if text != BEST_BEFORE_EN and not text.startswith("Lot ") else 21 * u, text)
			d.text((cx - d.textlength(text, font=f) / 2, y), text, font=f, fill=0)
			y += block_lh

	# barcode
	if bars:
		target = 0.6 * W
		mw = max(1, int(target // len(bars)))
		if mw * len(bars) > W - 2 * mx:
			mw = max(1, (W - 2 * mx) // len(bars))
		x0 = round(W / 2 - mw * len(bars) / 2)
		yb = H - bottom - bottom_block + round(14 * u)
		x, i = x0, 0
		while i < len(bars):
			j = i
			while j < len(bars) and bars[j] == bars[i]:
				j += 1
			if bars[i] == "1":
				d.rectangle([x, yb, x + (j - i) * mw - 1, yb + bar_h], fill=0)
			x += (j - i) * mw
			i = j
		f = _font("regular", bar_txt_px)
		d.text((W / 2 - d.textlength(bar_text, font=f) / 2, yb + bar_h + round(4 * u)), bar_text, font=f, fill=0)

	if label.get("banner"):
		f = _font("bold", 16 * u)
		tw = d.textlength(label["banner"], font=f)
		pad = round(6 * u)
		x1, y1 = W - mx - tw - 2 * pad, round(0.015 * H)
		d.rectangle([x1, y1, W - mx, y1 + 16 * u + 2 * pad], fill=0)
		d.text((x1 + pad, y1 + pad), label["banner"], font=f, fill=1)
	return img


# relative text sizes on the small kitchen date labels (P15b), as a share of the label height
KITCHEN_SIZES = {"title": 0.135, "sub": 0.11, "row": 0.095, "big": 0.12, "small": 0.075}
KITCHEN_BOLD = {"title", "big"}


def render_kitchen(lines: list[tuple[str, str]], width_mm: float = 50, height_mm: float = 30,
                   dpi: int = 203) -> Image.Image:
	"""A small kitchen date label (date_labels.kitchen_lines) as a 1-bit landscape
	image. Text shrinks until everything fits; long lines wrap."""
	W = round(max(width_mm, height_mm) / 25.4 * dpi)
	H = round(min(width_mm, height_mm) / 25.4 * dpi)
	img = Image.new("1", (W, H), 1)
	d = ImageDraw.Draw(img)
	m = max(4, round(0.04 * H))
	width = W - 2 * m

	def plan(scale: float):
		rows, y = [], m
		for style, text in lines:
			if not text:
				continue
			px = KITCHEN_SIZES.get(style, KITCHEN_SIZES["row"]) * H * scale
			f = _font("bold" if style in KITCHEN_BOLD else "regular", px, text)
			for part in _wrap(d, text, f, width):
				rows.append((y, part, f, style))
				y += round(px * 1.18)
		return rows, y

	scale = 1.0
	rows, bottom = plan(scale)
	while bottom > H - m and scale > 0.45:
		scale -= 0.05
		rows, bottom = plan(scale)
	for y, text, f, style in rows:
		if style == "big":  # the use-by line in reverse (white on black), so it stands out
			tw = d.textlength(text, font=f)
			d.rectangle([m - 2, y - 1, m + tw + 2, y + f.size + 2], fill=0)
			d.text((m, y), text, font=f, fill=1)
		else:
			d.text((m, y), text, font=f, fill=0)
	return img


def for_printer(img: Image.Image, width_mm: float, height_mm: float) -> Image.Image:
	"""Turn the landscape label a quarter turn for rolls fed narrow side first."""
	if width_mm < height_mm:
		return img.transpose(Image.Transpose.ROTATE_90)
	return img


def to_png_b64(img: Image.Image) -> str:
	buf = io.BytesIO()
	img.save(buf, format="PNG", optimize=True)
	return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------- ZPL ----------

def _count(n: int) -> str:
	"""ZPL repeat count: G..Y = 1..19, g..z = 20..400 (added together)."""
	out = "z" * (n // 400)
	n %= 400
	if n >= 20:
		out += chr(ord("g") + n // 20 - 1)
		n %= 20
	if n:
		out += chr(ord("G") + n - 1)
	return out


def _compress_row(hexrow: str) -> str:
	stripped = hexrow.rstrip("0")
	tail = "," if len(stripped) < len(hexrow) else ""
	if not tail:
		stripped_f = hexrow.rstrip("F")
		if len(stripped_f) < len(hexrow) - 1:
			stripped, tail = stripped_f, "!"
	out, i = [], 0
	while i < len(stripped):
		j = i
		while j < len(stripped) and stripped[j] == stripped[i]:
			j += 1
		run = j - i
		out.append((_count(run) if run > 1 else "") + stripped[i])
		i = j
	return "".join(out) + tail


def to_zpl(img: Image.Image, copies: int = 1) -> str:
	"""A full ^XA..^XZ label with the picture as a compressed ^GFA graphic."""
	img = img.convert("1")
	w, h = img.size
	bpr = (w + 7) // 8
	raw = img.tobytes()  # 1 bit per dot, 1 = white
	rows, prev = [], None
	for r in range(h):
		row = bytes(255 - b for b in raw[r * bpr:(r + 1) * bpr])
		# padding bits past the image edge are white
		if w % 8:
			row = row[:-1] + bytes([row[-1] & (0xFF << (8 - w % 8)) & 0xFF])
		hx = row.hex().upper()
		rows.append(":" if hx == prev else _compress_row(hx))
		prev = hx
	total = bpr * h
	return (
		f"^XA^PW{w}^LL{h}^LH0,0^PON^FO0,0^GFA,{total},{total},{bpr},{''.join(rows)}^FS"
		f"^PQ{max(1, int(copies))}^XZ\n"
	)


def zpl_graphic_to_rows(zpl: str) -> list[str]:
	"""Decode the ^GFA graphic of `to_zpl` back to hex rows (used by the tests)."""
	start = zpl.index("^GFA,") + 5
	total, _, bpr, rest = zpl[start:].split(",", 3)
	data = rest[: rest.index("^FS")]
	width = int(bpr) * 2
	rows, cur, n, prev = [], "", 0, None

	def end_row(fill=None):
		nonlocal cur, prev
		if fill is not None:
			cur = cur + fill * (width - len(cur))
		rows.append(cur)
		prev, cur = cur, ""

	for ch in data:
		if "G" <= ch <= "Y":
			n += ord(ch) - ord("G") + 1
		elif "g" <= ch <= "z":
			n += (ord(ch) - ord("g") + 1) * 20
		elif ch == ",":
			end_row("0")
		elif ch == "!":
			end_row("F")
		elif ch == ":":
			cur = prev
			end_row()
		else:
			cur += ch * (n or 1)
			n = 0
			if len(cur) == width:
				end_row()
	return rows
