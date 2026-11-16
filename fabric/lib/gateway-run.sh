#!/usr/bin/env bash
# Shared by fabric/gateway-check.sh, fabric/history-check.sh and fabric/spike-latency.sh:
# where the ledger-gateway scripts run (host Node, else the pinned `spike` image) and how they
# fail. Source it after setting FABRIC_DIR; it runs nothing by itself.
#
# The probes below are functions so that tests/scripts can replace them.

unavailable() {
  echo "error: environment unavailable: $*" >&2
  exit 1
}

wallet_present() { [[ -f "${FABRIC_DIR}/wallet/peer0-org1-tls-ca.crt" ]]; }
runtime_prepared() { [[ -f "${FABRIC_DIR}/.runtime/ca.env" ]]; }
host_can_run() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 \
    && [[ -d "${FABRIC_DIR}/../ledger-gateway/node_modules/typescript" ]]
}

# run_gateway_script <npm script> [docker run options...]
# Compiles first, so the script always runs the sources you have. The options (for example
# `-e NAME` to hand a variable to the container) apply to the container branch only.
# Exit status: that of the npm script; 1 when there is no wallet, no way to run Node, or the
# build fails.
run_gateway_script() {
  local script=$1
  shift
  wallet_present || unavailable "no wallet. Run fabric/network.sh start, then fabric/enroll-identities.sh."
  if host_can_run; then
    cd "${FABRIC_DIR}/../ledger-gateway"
    npm run build || unavailable "the TypeScript build failed."
    npm run "${script}"
  elif runtime_prepared; then
    cd "${FABRIC_DIR}"
    local spike=(docker compose --project-name saam-medtrace --env-file .runtime/ca.env
      -f compose/compose.yaml --profile spike run -T --rm --no-deps "$@" --entrypoint npm spike)
    "${spike[@]}" run build || unavailable "the TypeScript build failed."
    "${spike[@]}" run "${script}"
  else
    unavailable "Node is not usable here and the Fabric runtime is not prepared."
  fi
}
