from happy_kitchen.hk_operations import pdf_ocr


def test_to_lines_makes_reader_lines_and_marker():
	data = {"orders": [{"po_number": "ab-12345", "delivery_date": "2026-11-21",
	                    "lines": [{"code": "RJ0056", "description": "Peanut Butter Dough", "qty": 2, "unit_price": 610},
	                              {"code": "", "description": "Cookie | Oat", "qty": 0, "unit_price": 1}]}]}
	text = pdf_ocr.to_lines(data)
	assert text.startswith("--- PO AB-12345 | 2026-11-21 ---")
	assert "RJ0056 | Peanut Butter Dough | 2 | @ 610" in text or "RJ0056 | Peanut Butter Dough | 2 |" in text
	assert text.splitlines()[-1] == pdf_ocr.MARKER
	assert "Oat" not in text


def test_to_lines_empty_when_no_usable_line():
	assert pdf_ocr.to_lines({"orders": [{"lines": [{"description": "x", "qty": 0}]}]}) == ""
	assert pdf_ocr.to_lines({}) == ""


def test_marker_is_unparsed_so_order_needs_review():
	from happy_kitchen.hk_operations import email_orders

	lines, unparsed = email_orders.parse_lines("--- PO X12345 | 2026-11-21 ---\nRJ0056 | Dough | 2\n" + pdf_ocr.MARKER)
	assert len(lines) == 1 and unparsed == [pdf_ocr.MARKER]
