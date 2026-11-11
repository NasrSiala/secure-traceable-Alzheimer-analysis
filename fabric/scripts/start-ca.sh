#!/bin/sh
# Start one Fabric CA using bootstrap credentials injected by Compose.
set -eu

if [ -z "${CA_BOOTSTRAP_USER:-}" ] || [ -z "${CA_BOOTSTRAP_PASSWORD:-}" ]; then
  echo "CA bootstrap credentials are missing." >&2
  exit 1
fi

exec fabric-ca-server start -b "${CA_BOOTSTRAP_USER}:${CA_BOOTSTRAP_PASSWORD}"
