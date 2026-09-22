#!/usr/bin/env bash
# Installs the runtime dependencies of every workspace Lambda into
# build/layer/python for the shared arm64 python3.14 layer. infra/lambda.tf
# zips it with archive_file, so this must run before tofu plan.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf build/layer
mkdir -p build/layer

uv export --frozen --all-packages --no-dev --no-emit-workspace --no-hashes \
  -o build/requirements.txt
uv pip install \
  --target build/layer/python \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.14 \
  --only-binary :all: \
  -r build/requirements.txt

find build/layer -name __pycache__ -type d -prune -exec rm -rf {} +
rm -f build/layer/python/.lock
# Console scripts carry the build interpreter's path in their shebang, and
# each dist-info RECORD holds their hashes, so both would make the layer hash
# differ between machines. Lambda never runs the scripts, and RECORD is only
# read to uninstall.
rm -rf build/layer/python/bin
find build/layer/python -path '*.dist-info/RECORD' -delete

echo "Built $(pwd)/build/layer"
