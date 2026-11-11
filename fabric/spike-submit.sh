#!/usr/bin/env bash
# Run ledger-gateway's spike:submit inside the Node 20 image when the host has no Node.
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${FABRIC_DIR}"

export SPIKE_IDENTITY="${SPIKE_IDENTITY:-agent-ingestion}"
export SPIKE_OP="${SPIKE_OP:-write}"
export SPIKE_KEY="${SPIKE_KEY:-attribute-probe}"

# Without the wallet there is nothing to sign with, and nothing to trust the peer by.
if [[ ! -f wallet/peer0-org1-tls-ca.crt ]]; then
  echo "error: no wallet. Run fabric/network.sh start, then fabric/enroll-identities.sh." >&2
  exit 1
fi

if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 \
  && [[ -f ../ledger-gateway/dist/spike-submit.js ]]; then
  cd ../ledger-gateway
  npm run spike:submit
  exit $?
fi

docker compose --project-name saam-medtrace --env-file .runtime/ca.env \
  -f compose/compose.yaml --profile spike run -T --rm --no-deps \
  -e SPIKE_IDENTITY -e SPIKE_OP -e SPIKE_KEY \
  spike
