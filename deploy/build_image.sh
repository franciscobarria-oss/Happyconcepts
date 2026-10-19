#!/usr/bin/env bash
# Build hk/erpnext-hrms:<app tag> on the server. Usage: deploy/build_image.sh v1.0.0
# 1) base image (frappe + erpnext + hrms at the pinned versions), only if missing
# 2) layer 2 with happy_kitchen cloned from the private repo franciscobarria-oss/happyconcepts at the given tag,
#    using the server's read-only deploy key ~/.ssh/happyconcepts_deploy
set -euo pipefail
HK_REF="${1:?usage: build_image.sh <happy_kitchen tag or branch>}"
TAG="${HK_TAG:-${HK_REF//\//-}}"  # docker tags can't contain "/" (branch names)
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
HK_REPO="git@github.com:franciscobarria-oss/happyconcepts.git"
# Pin the build to the commit the ref points at now, so a moved branch is always cloned again.
HK_COMMIT=$(GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" git ls-remote "$HK_REPO" \
	"refs/heads/$HK_REF" "refs/tags/$HK_REF" | awk -v r="$HK_REF" '{c[$2]=$1}
	END { b="refs/heads/" r; t="refs/tags/" r; if (b in c) print c[b]; else if ((t "^{}") in c) print c[t "^{}"]; else print c[t] }')
[ -n "$HK_COMMIT" ] || { echo "No branch or tag $HK_REF in $HK_REPO" >&2; exit 1; }
DOCKER_BUILDKIT=1 docker build --ssh default="$KEY" \
	--build-arg BASE_IMAGE="$BASE" --build-arg HK_REF="$HK_REF" --build-arg HK_COMMIT="$HK_COMMIT" \
	-t "hk/erpnext-hrms:${TAG}" -f "$HERE/Containerfile.app" "$HERE"
echo "Built hk/erpnext-hrms:${TAG} from ${HK_REF} (${HK_COMMIT:0:7}) on ${BASE}"
