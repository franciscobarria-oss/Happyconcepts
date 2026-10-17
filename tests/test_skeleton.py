import os

import pytest

from happy_kitchen import hooks
from happy_kitchen.setup import block_files

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "happy_kitchen")


def test_requires_erpnext_and_hrms():
	assert hooks.required_apps == ["erpnext", "hrms"]


def test_asset_urls_carry_version():
	url = hooks._asset("js/x.js")
	assert url == f"/assets/happy_kitchen/js/x.js?v={hooks._HK_ASSET_VERSION}"
	for u in hooks.app_include_css + hooks.app_include_js:
		assert u.endswith(f"?v={hooks._HK_ASSET_VERSION}")


def test_modules_have_packages():
	with open(os.path.join(APP, "modules.txt"), encoding="utf-8") as f:
		modules = [m.strip() for m in f if m.strip()]
	assert modules == ["Recipe Management", "HK Operations"]
	for m in modules:
		pkg = os.path.join(APP, m.lower().replace(" ", "_"), "__init__.py")
		assert os.path.exists(pkg), pkg


def test_patches_txt_has_both_sections():
	with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as f:
		text = f.read()
	assert "[pre_model_sync]" in text and "[post_model_sync]" in text
	assert text.index("[pre_model_sync]") < text.index("[post_model_sync]")


def test_read_block(tmp_path):
	(tmp_path / "b.html").write_text("<div>你好</div>", encoding="utf-8")
	(tmp_path / "b.css").write_text(".x{}", encoding="utf-8")
	v = block_files.read_block("b", str(tmp_path))
	assert v == {"html": "<div>你好</div>", "script": "", "style": ".x{}"}
	with pytest.raises(FileNotFoundError):
		block_files.read_block("missing", str(tmp_path))


def test_needs_update():
	wanted = {"html": "a", "script": "", "style": ""}
	assert not block_files.needs_update({"html": "a", "script": None, "style": ""}, wanted)
	assert block_files.needs_update({"html": "b", "script": "", "style": ""}, wanted)
