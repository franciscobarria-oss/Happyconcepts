"""Fresh installs skip patches, so after_install must run every post_model_sync patch itself."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "happy_kitchen"


def post_model_sync_patches():
	section, found = None, []
	for line in (APP / "patches.txt").read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if line.startswith("[") and line.endswith("]"):
			section = line[1:-1]
		elif line and not line.startswith("#") and section == "post_model_sync":
			found.append(line.split()[0])
	return found


def install_patches():
	tree = ast.parse((APP / "setup" / "install.py").read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "INSTALL_PATCHES" for t in node.targets):
			return ast.literal_eval(node.value)
	raise AssertionError("INSTALL_PATCHES not found in setup/install.py")


def test_after_install_runs_every_post_model_sync_patch():
	assert install_patches() == post_model_sync_patches()


def test_install_patches_exist():
	for path in install_patches():
		assert (APP.parent / (path.replace(".", "/") + ".py")).is_file(), path
