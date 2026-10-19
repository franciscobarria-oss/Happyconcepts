from happy_kitchen import theme_rules as t


def test_site_config_overrides_setting():
	assert t.theme_on(0, 1) is False
	assert t.theme_on(1, 0) is True
	assert t.theme_on("1", None) is True
	assert t.theme_on(None, 1) is True
	assert t.theme_on(None, None) is False
	assert t.theme_on(None, "0") is False


def test_toggle_languages():
	assert t.valid_language("en") and t.valid_language("zh-TW")
	assert not t.valid_language("zh") and not t.valid_language("fr")
