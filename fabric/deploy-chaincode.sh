#!/usr/bin/env bash
# Install, approve and commit the provenance chaincode definition on the running medtrace
# network. It prints PACKAGE_ORG1 and PACKAGE_ORG2 on stdout. It needs the chaincode packages
# that fabric/enroll-identities.sh writes under .runtime/cc, which also builds the chaincode
# and starts its services: run that script, not this one, to bring a network up.
# Safe to repeat: fabric/scripts/deploy-chaincode.sh checks the committed definition.
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${FABRIC_DIR}"

if [[ ! -f .runtime/ca.env ]]; then
  echo "error: the medtrace network is not prepared. Run fabric/network.sh start, then fabric/enroll-identities.sh." >&2
  exit 1
fi

for org in org1 org2; do
  if [[ ! -f ".runtime/cc/${org}.tgz" ]]; then
    echo "error: .runtime/cc/${org}.tgz is missing. fabric/enroll-identities.sh builds the chaincode and writes its packages." >&2
    exit 1
  fi
done

exec docker compose --project-name saam-medtrace --env-file .runtime/ca.env \
  -f compose/compose.yaml --profile tools run -T --rm --no-deps \
  tools /work/scripts/deploy-chaincode.sh
