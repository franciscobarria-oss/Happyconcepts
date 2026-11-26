from happy_kitchen.recipe_management import document_rules as r


def test_clean_pads_rows_and_drops_empty():
	d = r.clean({"text": " Hi ", "tables": [
		{"title": "T", "headers": ["A", "B"], "rows": [["1"], ["2", "3", "4"], ["", ""]]},
		{"rows": [[]]}], "unclear": ["", "x"]})
	assert d["text"] == "Hi" and d["unclear"] == ["x"] and len(d["tables"]) == 1
	t = d["tables"][0]
	assert t["headers"] == ["A", "B", ""] and t["rows"] == [["1", "", ""], ["2", "3", "4"]]


def test_no_headers_and_none_values():
	t = r.clean({"tables": [{"headers": ["", ""], "rows": [[None, 5]]}]})["tables"][0]
	assert t["headers"] == [] and t["rows"] == [["", "5"]]
	assert r.clean(None) == {"text": "", "tables": [], "unclear": []}


def test_csv_and_tsv():
	t = {"headers": ["Name", "Qty"], "rows": [['a,"b"', "1"], ["牛奶", "2\t3"]]}
	assert r.to_csv(t) == 'Name,Qty\r\n"a,""b""",1\r\n牛奶,2\t3\r\n'
	assert r.to_tsv(t) == "Name\tQty\na,\"b\"\t1\n牛奶\t2 3"


def test_queue_rules():
	assert r.MAX_ATTEMPTS == 3
	assert r.is_stale("Reading", 0, 2000) and not r.is_stale("Reading", 0, 100)
	assert not r.is_stale("Done", 0, 99999) and not r.is_stale("Reading", None, 99999)
	assert r.is_expired(0, 31 * 86400) and not r.is_expired(0, 29 * 86400)
