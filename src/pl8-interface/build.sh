#!/usr/bin/env bash
# Builds dist/pl8-interface.zip for the arm64 python3.14 Lambda runtime.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf build dist
mkdir -p build/package dist

uv export --frozen --no-dev --no-hashes -o build/requirements.txt
uv pip install \
  --target build/package \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.14 \
  --only-binary :all: \
  -r build/requirements.txt

cp -r src/pl8_interface build/package/
find build/package -name __pycache__ -type d -prune -exec rm -rf {} +
rm -f build/package/.lock

# Fixed mtimes and sorted entries so an unchanged build hashes the same,
# keeping the Lambda's source_code_hash stable.
export TZ=UTC
find build/package -exec touch -h -t 198001010000 {} +
(cd build/package && find . -type f | LC_ALL=C sort | zip -X -D -q ../../dist/pl8-interface.zip -@)

echo "Built $(pwd)/dist/pl8-interface.zip"
