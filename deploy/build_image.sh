#!/usr/bin/env bash
# Build hk/erpnext-hrms:<app tag> on the server. Usage: deploy/build_image.sh v1.0.0
# 1) base image (frappe + erpnext + hrms at the pinned versions), only if missing
# 2) layer 2 with happy_kitchen cloned from the private repo franciscobarria-oss/happyconcepts at the given tag,
#    using the server's read-only deploy key ~/.ssh/happyconcepts_deploy
set -euo pipefail
HK_REF="${1:?usage: build_image.sh <happy_kitchen tag or branch>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/versions.env"
FRAPPE_DOCKER="${FRAPPE_DOCKER:-/opt/frappe_docker}"
BASE="hk/erpnext-hrms-base:${FRAPPE_BRANCH}"

if ! docker image inspect "$BASE" >/dev/null 2>&1; then
	APPS_JSON=$(mktemp)
	cat > "$APPS_JSON" <<JSON
[{"url": "https://github.com/frappe/erpnext", "branch": "${ERPNEXT_BRANCH}"},
 {"url": "https://github.com/frappe/hrms", "branch": "${HRMS_BRANCH}"}]
JSON
	DOCKER_BUILDKIT=1 docker build \
		--build-arg FRAPPE_PATH=https://github.com/frappe/frappe \
		--build-arg FRAPPE_BRANCH="${FRAPPE_BRANCH}" \
		--secret id=apps_json,src="$APPS_JSON" \
		-t "$BASE" -f "$FRAPPE_DOCKER/images/layered/Containerfile" "$FRAPPE_DOCKER"
	rm -f "$APPS_JSON"
fi

KEY="${HK_DEPLOY_KEY:-$HOME/.ssh/happyconcepts_deploy}"
DOCKER_BUILDKIT=1 docker build --ssh default="$KEY" \
	--build-arg BASE_IMAGE="$BASE" --build-arg HK_REF="$HK_REF" \
	-t "hk/erpnext-hrms:${HK_REF}" -f "$HERE/Containerfile.app" "$HERE"
echo "Built hk/erpnext-hrms:${HK_REF} on ${BASE}"
