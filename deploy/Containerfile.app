# syntax=docker/dockerfile:1
# Layer 2: adds the happy_kitchen app (from GitHub, at a tag) and the CJK font on top of the
# base image hk/erpnext-hrms-base:<frappe version> (frappe + erpnext + hrms, built by build_image.sh).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk git openssh-client \
 && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe/frappe-bench
ARG HK_REF
# The repo is private: the clone uses the server's read-only deploy key through `docker build --ssh`,
# so no key or token ends up in the image.
ARG HK_REPO=git@github.com:franciscobarria-oss/happyconcepts.git
RUN --mount=type=ssh,uid=1000 mkdir -p -m 0700 ~/.ssh \
 && ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null \
 && git clone --depth 1 --branch "${HK_REF}" "${HK_REPO}" apps/happy_kitchen \
 && rm -rf apps/happy_kitchen/.git
# Assets are baked into /home/frappe/frappe-bench/assets in v16 images; the entrypoint links sites/assets to it.
RUN (./env/bin/pip --version >/dev/null 2>&1 && ./env/bin/pip install --no-cache-dir -e apps/happy_kitchen \
     || uv pip install --python ./env/bin/python -e apps/happy_kitchen) \
 && ln -sfn /home/frappe/frappe-bench/apps/happy_kitchen/happy_kitchen/public assets/happy_kitchen \
 && (grep -qx happy_kitchen sites/apps.txt || echo happy_kitchen >> sites/apps.txt) \
 && ./env/bin/python -c "import erpnext, hrms, barcode, happy_kitchen.hooks; print('import ok')"
