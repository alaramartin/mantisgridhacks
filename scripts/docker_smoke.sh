#!/usr/bin/env bash
# What `make docker` does, for machines without make (Person 2's Windows box).
# Builds the submission image and runs it exactly as the judges will: 2 CPU, 8 GB,
# dataset read-only, output to a bind mount, no network assumptions beyond the API.
#
#   scripts/docker_smoke.sh [N] [AGENT]
#
# On Git Bash, MSYS rewrites /data and /out into Windows paths before docker sees
# them, which silently mounts the wrong thing -- MSYS_NO_PATHCONV=1 stops that.
set -euo pipefail

N="${1:-2}"
AGENT="${2:-agents.origin}"
SET="${SET:-Market-cloudbed-1}"
# docker is a Windows binary here, so it needs a Windows path: `pwd -W` where
# Git Bash provides it, plain `pwd` on Linux/macOS.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$(pwd -W 2>/dev/null)" || ROOT="$(pwd)"

export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"

docker build -t rca-submission "$ROOT"
rm -rf "$ROOT/out/docker" && mkdir -p "$ROOT/out/docker"

MSYS_NO_PATHCONV=1 docker run --rm --cpus 2 --memory 8g \
  -e FEATHERLESS_API_KEY -e FEATHERLESS_BASE_URL -e ORIGIN_MODE -e ORIGIN_FIXTURE \
  -v "$ROOT/data/$SET":/data:ro -v "$ROOT/out/docker":/out \
  rca-submission \
  python run.py --dataset /data --queries /data/dev/query_dev.csv \
    --out /out --limit "$N" --agent "$AGENT"

echo "evidence files: $(ls "$ROOT/out/docker/evidence" | wc -l)"
