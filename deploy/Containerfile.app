# syntax=docker/dockerfile:1
# Layer 2: adds the happy_kitchen app (from GitHub, at a tag) and the CJK font on top of the
# base image hk/erpnext-hrms-base:<frappe version> (frappe + erpnext + hrms, built by build_image.sh).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk git \
 && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe/frappe-bench
ARG HK_REF
ARG HK_REPO=https://github.com/franciscobarria-oss/happyconcepts
RUN git clone --depth 1 --branch "${HK_REF}" "${HK_REPO}" apps/happy_kitchen \
 && rm -rf apps/happy_kitchen/.git
RUN (./env/bin/pip --version >/dev/null 2>&1 && ./env/bin/pip install --no-cache-dir -e apps/happy_kitchen \
     || uv pip install --python ./env/bin/python -e apps/happy_kitchen) \
 && ln -sfn ../apps/happy_kitchen/happy_kitchen/public sites/assets/happy_kitchen \
 && (grep -qx happy_kitchen sites/apps.txt || echo happy_kitchen >> sites/apps.txt) \
 && ./env/bin/python -c "import erpnext, hrms, barcode, happy_kitchen.hooks; print('import ok')"
