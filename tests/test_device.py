"""Pure device rules of public/js/hk_device.js, run through node (no frappe import)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "happy_kitchen" / "public" / "js" / "hk_device.js"


def run(expr):
	if not shutil.which("node"):
		pytest.skip("node not installed")
	code = f"const m=require({json.dumps(str(JS))});console.log(JSON.stringify({expr}))"
	return json.loads(subprocess.check_output(["node", "-e", code], text=True))


def test_classify():
	assert run("m.classify(1920,1080,false)") == "desktop"
	assert run("m.classify(1366,1024,true)") == "tablet"
	assert run("m.classify(768,1024,true)") == "tablet"
	assert run("m.classify(390,844,true)") == "phone"
	assert run("m.classify(1440,900,false)") == "desktop"  # touch laptop = fine pointer
