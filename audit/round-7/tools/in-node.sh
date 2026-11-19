#!/usr/bin/env bash
# Audit helper: run a command in a throwaway copy of a Node package, inside the pinned image.
# Usage: audit/round-7/tools/in-node.sh <package dir> '<shell command run in the copy>' [source dir to mount]
# The copy is installed with `npm ci --ignore-scripts` and then built (tsc -p tsconfig.json) when
# the command needs dist/. Nothing is written to the checkout.
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
IMAGE='node:20.20.2-bookworm@sha256:8f693eaa7e0a8e71560c9a82b55fd54c2ae920a2ba5d2cde28bac7d1c01c9ba5'
dir=$1
cmd=$2
src=${3:-$(cd "$dir" && pwd -W 2>/dev/null || pwd)}
docker run --rm -v "${src}:/src:ro" "${IMAGE}" bash -c \
  "set -e; mkdir /tmp/w; cd /src; tar --exclude=./node_modules --exclude=./dist --exclude=./dist-test -cf - . | tar -xf - -C /tmp/w; cd /tmp/w; npm ci --ignore-scripts --no-fund --no-audit >/dev/null 2>&1; ${cmd}"
