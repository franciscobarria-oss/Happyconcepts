import base64

from happy_kitchen.hk_operations import email_orders as eo
from happy_kitchen.hk_operations import sku


def _b64(text):
	return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_parse_sender_and_allow_list():
	assert eo.parse_sender('"Cafe A" <Orders@CafeA.com>') == ("Cafe A", "orders@cafea.com")
	assert eo.parse_sender("") == ("", "")
	assert eo.sender_allowed("a@x.com", "")
	assert eo.sender_allowed("a@x.com", "b@y.com, a@x.com")
	assert eo.sender_allowed("a@x.com", "@x.com")
	assert not eo.sender_allowed("a@evil-x.com", "@x.com\nb@y.com")


def test_body_text_prefers_plain_and_strips_html():
	plain = {"mimeType": "multipart/alternative", "parts": [
		{"mimeType": "text/plain", "body": {"data": _b64("12 x Brownie\r\n\r\nThanks")}},
		{"mimeType": "text/html", "body": {"data": _b64("<p>ignored</p>")}}]}
	assert eo.body_text(plain) == "12 x Brownie\nThanks"
	rich = {"mimeType": "text/html", "body": {"data": _b64("<table><tr><td>CK-1</td><td>Cookie</td><td>24</td></tr></table>")}}
	assert "CK-1 | Cookie | 24" in eo.body_text(rich).replace("  ", " ")


def test_parse_lines_formats():
	text = "\n".join([
		"Hi team, please send for Friday:",
		"Code | Product | Qty",
		"CK-001 | Butter cookie | 24",
		"BR-7 | Sourdough loaf | 6 pcs",
		"12 x Chocolate brownie",
		"Almond croissant x 30",
		"5 x [PS-12] Pistachio swirl",
		"BR-9 - Rye loaf x 4",
		"Thanks!",
	])
	lines, unparsed = eo.parse_lines(text)
	assert unparsed == []
	assert [(l["external_sku"], l["description"], l["qty"]) for l in lines] == [
		("CK-001", "Butter cookie", 24), ("BR-7", "Sourdough loaf", 6), ("", "Chocolate brownie", 12),
		("", "Almond croissant", 30), ("PS-12", "Pistachio swirl", 5), ("BR-9", "Rye loaf", 4)]


def test_parse_lines_flags_what_it_cannot_read():
	lines, unparsed = eo.parse_lines("CK-001 | Butter cookie | a dozen\n0 x Nothing\nJust some chatter")
	assert lines == []
	assert unparsed == ["CK-001 | Butter cookie | a dozen", "0 x Nothing"]


def test_next_internal_sku():
	assert sku.next_code([]) == "SKU-0001"
	assert sku.next_code(["SKU-0009", "SKU-0002", "ING-099", "SKU-x"]) == "SKU-0010"


def test_strip_quoted_keeps_only_the_new_words():
	reply = "Please make it 18 x Brownie\n\nOn Mon, 19 Oct 2026 at 10:00, Amy <a@x.com> wrote:\n> 12 x Brownie\n> Thanks"
	assert eo.strip_quoted(reply) == "Please make it 18 x Brownie\n"
	assert eo.strip_quoted("> 12 x Brownie\n6 x Scone") == "6 x Scone"
	assert eo.strip_quoted("12 x Brownie\n-----Original Message-----\n12 x Brownie") == "12 x Brownie"


def test_table_to_lines_uses_the_header_row():
	rows = [
		["Purchase Order 123", None, None],
		["Item Code", "Description", "Qty", "Unit"],
		["CK-001", "Butter cookie", "12", "box"],
		["", "Delivery note", "", ""],
		["CK-002", "Brownie\ntray", "1,200", "pcs"],
		["", "Total", "1212", ""],
		["CK-003", "Zero", "0", "pcs"],
	]
	assert eo.table_to_lines(rows) == ["CK-001 | Butter cookie | 12", "CK-002 | Brownie tray | 1200"]
	lines, unparsed = eo.parse_lines("\n".join(eo.table_to_lines(rows)))
	assert [(l["external_sku"], l["description"], l["qty"]) for l in lines] == [
		("CK-001", "Butter cookie", 12), ("CK-002", "Brownie tray", 1200)]
	assert unparsed == []


def test_table_without_a_quantity_column_gives_nothing():
	assert eo.table_to_lines([["Name", "Price"], ["Brownie", "5"]]) == []


def test_table_description_only():
	assert eo.table_to_lines([["Product", "Quantity"], ["Brownie", "6"]]) == ["Brownie | 6"]


def test_pdf_attachments_and_joined_text():
	payload = {"mimeType": "multipart/mixed", "parts": [
		{"mimeType": "text/plain", "body": {"data": "SGk="}},
		{"mimeType": "application/pdf", "filename": "PO-9.pdf", "body": {"attachmentId": "att1"}},
		{"mimeType": "image/png", "filename": "logo.png", "body": {"attachmentId": "att2"}},
	]}
	atts = eo.pdf_attachments(payload)
	assert [(a["filename"], a["attachment_id"]) for a in atts] == [("PO-9.pdf", "att1")]
	text = eo.join_attachment_text("Hi", [("PO-9.pdf", "CK-001 | Cookie | 3"), ("scan.pdf", "")])
	assert "--- Attachment: PO-9.pdf ---" in text and "--- Attachment: scan.pdf ---" in text
	lines, unparsed = eo.parse_lines(text)
	assert [(l["external_sku"], l["qty"]) for l in lines] == [("CK-001", 3)] and unparsed == []


LAYOUT_A = """Purchase Order
Supplier Item Unit
No. Description No. Quantity Packing Size Unit Price Amount
Butter cookie box 123456789 12 box 10.50 126.00
tin of 24
Brownie tray 987654321 6 pcs 99.00 594.00
Total HKD 720.00
Page 1 of 1
"""


def test_text_item_lines_reads_positioned_text_with_wrapping_descriptions():
	lines = eo.text_item_lines(LAYOUT_A)
	assert lines == ["123456789 | Butter cookie box tin of 24 | 12 | @ 10.5", "987654321 | Brownie tray | 6 | @ 99"]
	parsed, unparsed = eo.parse_lines("\n".join(lines))
	assert [(l["external_sku"], l["description"], l["qty"]) for l in parsed] == [
		("123456789", "Butter cookie box tin of 24", 12), ("987654321", "Brownie tray", 6)]
	assert [l["po_rate"] for l in parsed] == [10.5, 99]
	assert unparsed == []


def test_text_item_lines_needs_the_header():
	assert eo.text_item_lines("Butter cookie 123456789 12 box 10.50 126.00") == []


def test_table_row_with_merged_order_lines_is_split():
	rows = [
		["Product Code", "Description", "Order Unit", "QTY", "Unit Price", "Total"],
		["1111111111 2222222222", "Flour 25kg\nSugar 10kg", "CS PK", "12.000 6.500", "9.99 5.00", "119.88 32.50"],
		["3333333333", "Eggs tray", "TR", "30.000", "4.00", "120.00"],
	]
	assert eo.table_to_lines(rows) == [
		"1111111111 | Flour 25kg | 12.000 | @ 9.99", "2222222222 | Sugar 10kg | 6.500 | @ 5", "3333333333 | Eggs tray | 30.000 | @ 4"]


def test_table_without_code_column_and_decimal_quantity():
	rows = [["Description", "Quantity", "Unit", "Unit Price", "Amount", "Del. Date"],
	        ["Lemon tart", "9.50", "Pcs", "12.00", "114.00", "21/Oct/2026"]]
	assert eo.table_to_lines(rows) == ["Lemon tart | 9.50 | @ 12"]


def test_up_to_eight_pdfs_are_listed():
	parts = [{"mimeType": "application/pdf", "filename": f"{i}.pdf", "body": {"attachmentId": f"a{i}"}} for i in range(6)]
	assert len(eo.pdf_attachments({"parts": parts})) == 6


def test_table_quantity_cell_with_its_unit():
	rows = [["Description", "Quantity", "Unit Price", "Amount"], ["Lemon tart", "9.50 Pcs", "12.00", "114.00"]]
	assert eo.table_to_lines(rows) == ["Lemon tart | 9.50 | @ 12"]


def test_text_items_without_item_code():
	text = "Description Quantity Unit Unit Price Amount Del. Date\nLemon tart large 9.50 Pcs 12.00 114.00 21/Oct/2026\nTotal: 114.00\n"
	assert eo.text_item_lines(text) == ["Lemon tart large | 9.50 | @ 12 | 2026-10-21"]


def test_text_item_with_its_own_date():
	text = "Description Quantity Unit Unit Price Amount Del. Date\nLemon tart 9.50 Pcs 12.00 114.00 21/Oct/2026\n"
	assert eo.text_item_lines(text) == ["Lemon tart | 9.50 | @ 12 | 2026-10-21"]
	lines, _ = eo.parse_lines("--- PO A1-12345 | 2026-10-25 ---\nLemon tart | 9.50 | @ 12 | 2026-10-21\nCake | 2")
	assert [(l["po_no"], l["delivery_date"], l["qty"], l["po_rate"]) for l in lines] == [
		("A1-12345", "2026-10-21", 9.5, 12), ("A1-12345", "2026-10-25", 2, 0)]


def test_total_lines_are_not_unparsed():
	lines, unparsed = eo.parse_lines("Total | 114.00\nSub Total 5 x 3\nBrownie | 4")
	assert [(l["description"], l["qty"]) for l in lines] == [("Brownie", 4)] and unparsed == []


def test_a_huge_cell_is_not_a_table_row_and_text_is_used():
	rows = [["Description", "Quantity", "Unit", "Unit Price", "Amount"],
	        ["Terms and conditions " * 40, "9.99", "x", "1", "2"]]
	assert eo.table_to_lines(rows) == []


def test_repeated_page_lines_are_read_once():
	assert eo.drop_repeats(["A | x | 1", "B | y | 2", "A | x | 1"]) == ["A | x | 1", "B | y | 2"]


def _page(po, rows):
	return f"Purchase Order\nPurchase No. {po}\nNo. Description No. Quantity Unit Unit Price Amount\n" + "\n".join(rows) + "\nTotal HKD 1.00\n"


def test_same_po_printed_twice_is_read_once_but_different_pos_are_kept():
	row = "Butter cookie 123456789 12 box 10.50 126.00"
	pages = [_page("AB1-0001", [row]), _page("AB1-0001", [row]), _page("AB1-0002", [row]), _page("AB1-0003", [row])]
	got = eo.text_item_pages(pages)
	assert [po for po, _, _ in got] == ["AB1-0001", "AB1-0002", "AB1-0003"]
	assert all(lines == ["123456789 | Butter cookie | 12 | @ 10.5"] for _, _, lines in got)


def test_table_that_continues_on_the_next_page_is_read_whole():
	p1 = "Description Quantity Unit Unit Price Amount\nCookie 123456789 1 box 1.00 1.00\n"
	p2 = "Page 2\nCake 987654321 2 box 2.00 4.00\nTotal 5.00\n"
	assert [l for _, _, ls in eo.text_item_pages([p1, p2]) for l in ls] == ["123456789 | Cookie | 1 | @ 1", "987654321 | Cake | 2 | @ 2"]


def test_wrapped_description_stays_short_and_terms_text_is_not_swallowed():
	text = ("Description Quantity Unit Unit Price Amount\nLemon tart 9.50 Pcs 12.00 114.00\n"
	        "Item Total: 114.00\n" + "Terms and conditions apply to every order. " * 30 + "\n")
	assert eo.text_item_lines(text) == ["Lemon tart | 9.50 | @ 12"]


def test_po_number():
	assert eo.po_number("ORDER NO.: A1234-56789 x") == "A1234-56789"
	assert eo.po_number("Purchase No. AB12-3456789") == "AB12-3456789"
	assert eo.po_number("nothing here") == ""


def test_signature_pipe_lines_are_not_unparsed():
	text = "Unit 1, Block 2 | 99 Some Road | Kowloon | Hong Kong\nTel: +852 1234 5678 | Email: a@b.com\nBrownie | 4"
	lines, unparsed = eo.parse_lines(text)
	assert [(l["description"], l["qty"]) for l in lines] == [("Brownie", 4)] and unparsed == []


def test_dates_and_delivery_date_of_a_page():
	assert eo.parse_date("21. October 2026") == "2026-10-21"
	assert eo.parse_date("21/Oct/2026") == "2026-10-21"
	assert eo.parse_date("21/10/2026") == "2026-10-21"
	assert eo.parse_date("2026-10-21") == "2026-10-21"
	assert eo.parse_date("31/02/2026") == "" and eo.parse_date("soon") == ""
	assert eo.delivery_date_of("Order Date 20 Oct 2026\nDelivery Date 25. October 2026\n") == "2026-10-25"
	assert eo.delivery_date_of("no dates") == ""


def test_po_markers_split_lines_by_po():
	text = "--- PO A-11111 | 2026-10-21 ---\nCookie | 1\n--- PO A-22222 | 2026-10-22 ---\nCookie | 3\nCake | 2"
	lines, _ = eo.parse_lines(text)
	assert [(l["po_no"], l["delivery_date"], l["qty"]) for l in lines] == [
		("A-11111", "2026-10-21", 1), ("A-22222", "2026-10-22", 3), ("A-22222", "2026-10-22", 2)]
	plain, _ = eo.parse_lines("Cookie | 1")
	assert plain[0]["po_no"] == "" and plain[0]["delivery_date"] == ""


def test_search_query_label_only():
	assert eo.search_query("Orders", 14) == 'label:"Orders" newer_than:14d'
	assert eo.search_query('Or"ders', 0, "") == 'label:"Orders" newer_than:14d'


def test_search_query_extra_senders():
	q = eo.search_query("Orders", 7, "plaza-network.com, @Shop.example\nbuyer@x.example plaza-network.com")
	assert q == '(label:"Orders" OR from:plaza-network.com OR from:shop.example OR from:buyer@x.example) newer_than:7d'


def test_search_query_drops_unsafe_entries():
	q = eo.search_query("Orders", 14, 'a.com) (label:"x" or ok.com')
	assert q == '(label:"Orders" OR from:ok.com) newer_than:14d'


def test_skip_reply():
	hdr = lambda **h: {"headers": [{"name": k.replace("_", "-"), "value": v} for k, v in h.items()]}
	f = eo.skip_reply
	own = "happyconceptsfood.hk"
	assert f("a@happyconceptsfood.hk", "Re: Order", hdr(), False, own)
	assert f("a@mail.happyconceptsfood.hk", "回覆: 訂單", hdr(), False, "@" + own)
	assert f("a@happyconceptsfood.hk", "Order", hdr(In_Reply_To="<x@y>"), False, own)
	assert not f("a@happyconceptsfood.hk", "Re: Order", hdr(), True, own)  # carries a PDF
	assert not f("a@happyconceptsfood.hk", "Fwd: PO 12", hdr(), False, own)  # a forward
	assert not f("a@nothappyconceptsfood.hk", "Re: Order", hdr(), False, own)
	assert not f("b@x.com", "Re: Order", hdr(), False, "a@x.com") and f("a@x.com", "RE: x", hdr(), False, "a@x.com")
	assert not f("a@happyconceptsfood.hk", "Re: Order", hdr(), False, "")


def test_review_reasons_by_status():
	assert eo.review_reasons("Draft order", 3, 0, True, 1, True)
	assert any("by hand" in r for r in eo.review_reasons("Done by hand", 0, 0, False, 0, False))
	assert eo.review_reasons("Needs review", 0, 0, False, 1, False) != eo.review_reasons("Needs review", 0, 0, False, 0, False)
	assert any("{unparsed} line(s)" in r for r in eo.review_reasons("Needs review", 3, 2, True, 1, True))
	assert eo.review_reasons("Failed", 0, 0, False, 0, False)


def test_review_reasons_order_confirmed():
	assert eo.review_reasons("Order confirmed", 2, 0, True, 1, True)


def test_unit_price_column_is_read():
	rows = [["Item Code", "Description", "Qty", "Unit Price (HKD)", "Amount"],
	        ["CK-001", "Butter cookie", "12", "1,050.50", "12,606.00"],
	        ["CK-002", "Brownie", "3", "", ""]]
	assert eo.table_to_lines(rows) == ["CK-001 | Butter cookie | 12 | @ 1050.5", "CK-002 | Brownie | 3"]
	lines, unparsed = eo.parse_lines("\n".join(eo.table_to_lines(rows)) + "\nCK-3 | Cake | 2 | @ 7.25\n4 x Scone")
	assert [(l["external_sku"], l["qty"], l["po_rate"]) for l in lines] == [
		("CK-001", 12, 1050.5), ("CK-002", 3, 0), ("CK-3", 2, 7.25), ("", 4, 0)]
	assert unparsed == []


def test_amount_or_total_column_is_not_the_unit_price():
	rows = [["Description", "Qty", "Amount"], ["Brownie", "3", "30.00"]]
	assert eo.table_to_lines(rows) == ["Brownie | 3"]
	assert eo.is_price_head("unit price (hkd)") and eo.is_price_head("單價") and not eo.is_price_head("amount")


def test_review_reasons_price_warnings():
	from happy_kitchen.hk_operations import order_prices as op

	got = eo.review_reasons("Draft order", 3, 0, True, 1, True, {op.DIFFERS: 2, op.USED: 1, op.NONE: 1})
	assert any("{differs} line(s)" in r for r in got) and any("{used} line(s)" in r for r in got)
	assert any("{none} line(s)" in r for r in got)
	assert not any("price" in r for r in eo.review_reasons("Draft order", 3, 0, True, 1, True, {op.SAME: 3}))
	assert not any("price" in r for r in eo.review_reasons("Ignored", 3, 0, True, 1, True, {op.DIFFERS: 1}))
