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
