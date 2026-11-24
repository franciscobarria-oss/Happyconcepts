from happy_kitchen.recipe_management import photo_recipe as p


def test_convert_units():
	assert p.convert(2, "tbsp") == (30, "ml", "written as 2 tbsp")
	assert p.convert(1, "斤") == (604.8, "g", "written as 1 斤")
	assert p.convert("250", "克") == (250.0, "g", "")
	assert p.convert(3, "隻")[1] == "piece"
	assert p.convert(5, "pinch") == (5.0, "", "unit as written: pinch")
	assert p.convert(None, "") == (0.0, "", "")
	assert p.convert(-4, "g")[0] == 0.0


def test_clean_drops_junk_and_keeps_chinese():
	d = p.clean({"title": " 曲奇 ", "ingredients": [{"name": "牛油", "qty": 250, "unit": "克"}, {"name": "", "qty": 1},
	                                              "bad", {"name": "Eggs", "qty": "x", "unit": "pcs", "note": "room temp"}],
	             "steps": ["Mix", "", "Bake"], "text": "t"})
	assert d["title"] == "曲奇"
	assert [i["name"] for i in d["ingredients"]] == ["牛油", "Eggs"]
	assert d["ingredients"][1] == {"name": "Eggs", "qty": 0.0, "uom": "piece", "note": "room temp"}
	assert d["steps"] == ["Mix", "Bake"]
	assert p.clean(None)["ingredients"] == []


def test_quantities_are_not_rounded_away():
	assert p.clean({"ingredients": [{"name": "egg", "qty": 0.025, "unit": "piece"}]})["ingredients"][0]["qty"] == 0.025


def test_to_text_prefers_transcription():
	assert p.to_text({"text": "abc"}) == "abc"
	t = p.to_text({"title": "Cake", "ingredients": [{"name": "Flour", "qty": 200, "uom": "g"}], "steps": ["Bake"]})
	assert "Flour 200 g" in t and "1. Bake" in t


ITEMS = [{"name": "ING-001", "item_name": "Butter", "item_name_zh": "牛油"},
         {"name": "ING-002", "item_name": "Butter Unsalted", "item_name_zh": ""},
         {"name": "ING-003", "item_name": "Plain Flour", "item_name_zh": "麵粉"},
         {"name": "ING-004", "item_name": "Plain Flour Organic", "item_name_zh": ""}]


def test_pick_match_exact_and_chinese():
	assert p.pick_match("butter", ITEMS) == "ING-001"
	assert p.pick_match("牛油", ITEMS) == "ING-001"
	assert p.pick_match("ING-003", ITEMS) == "ING-003"


def test_pick_match_prefers_shorter_and_refuses_ties():
	assert p.pick_match("plain", ITEMS) == "ING-003"
	assert p.pick_match("sugar", ITEMS) is None
	twin = [{"name": "A", "item_name": "Cream X"}, {"name": "B", "item_name": "Cream Y"}]
	assert p.pick_match("cream", twin) is None


def test_json_schema_lowercase():
	s = p.json_schema()
	assert s["type"] == "object" and s["properties"]["ingredients"]["items"]["type"] == "object"
	assert p.SCHEMA["type"] == "OBJECT"
