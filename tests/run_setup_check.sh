#!/bin/sh
# Load the helper in the Home Assistant image from hacs.json.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
version=$(sed -n 's/.*"homeassistant"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$root/hacs.json")
if [ -z "$version" ]; then
  echo "hacs.json has no homeassistant version" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
exec docker run --rm \
  --entrypoint python3 \
  -e PYTHONUNBUFFERED=1 \
  -v "$root/custom_components/boiler_four_way_valve:/component:ro" \
  -v "$root/tests/setup_check.py:/setup_check.py:ro" \
  "ghcr.io/home-assistant/home-assistant:${version}" \
  /setup_check.py /component
