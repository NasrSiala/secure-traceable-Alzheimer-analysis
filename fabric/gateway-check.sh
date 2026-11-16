#!/usr/bin/env bash
# Run the gateway create/read check (T2.6). It compiles first, so it always checks the sources
# you have. Uses host Node when it can build, otherwise the spike image. Exit status:
#   0  every answer was as expected
#   1  a wrong answer, no wallet, or a failed build
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${FABRIC_DIR}"

export GATEWAY_SCENARIO="${GATEWAY_SCENARIO:-flow}"

unavailable() {
  echo "error: environment unavailable: $*" >&2
  exit 1
}

# Kept as functions so that tests/scripts can replace them.
wallet_present() { [[ -f wallet/peer0-org1-tls-ca.crt ]]; }
runtime_prepared() { [[ -f .runtime/ca.env ]]; }
host_can_run() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 \
    && [[ -d ../ledger-gateway/node_modules/typescript ]]
}

check_on_host() {
  cd ../ledger-gateway
  npm run build || unavailable "the TypeScript build failed."
  npm run check:gateway
}

check_in_container() {
  local spike=(docker compose --project-name saam-medtrace --env-file .runtime/ca.env
    -f compose/compose.yaml --profile spike run -T --rm --no-deps -e GATEWAY_SCENARIO
    --entrypoint npm spike)
  "${spike[@]}" run build || unavailable "the TypeScript build failed."
  "${spike[@]}" run check:gateway
}

main() {
  wallet_present || unavailable "no wallet. Run fabric/network.sh start, then fabric/enroll-identities.sh."
  if host_can_run; then
    check_on_host
  elif runtime_prepared; then
    check_in_container
  else
    unavailable "Node is not usable here and the Fabric runtime is not prepared."
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
