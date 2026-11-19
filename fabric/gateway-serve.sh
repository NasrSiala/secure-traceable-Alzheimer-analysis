#!/usr/bin/env bash
# Serve ledger-gateway (the real `dist/server.js`, IF-09) for tests that call it over HTTP, such
# as tests/integrity/test_no_phi_onchain.py (T2.9). It compiles first, then stays in the
# foreground until it is stopped. Uses host Node when it can build, otherwise the spike image,
# where the port is published on 127.0.0.1 only and the container is named
# saam-medtrace-gateway-serve (remove it with `docker rm -f` if the script was killed).
#
# Stopping it: with host Node the gateway is a grandchild of this script (npm, then node), and a
# signal to the script alone leaves it running. Stop the whole process group (POSIX) or job object
# (Windows), as tests/integrity/process_tree.py does.
#
#   GATEWAY_SERVE_TOKEN_DIR  directory that holds tokens.json (identity -> token), required
#   GATEWAY_SERVE_PORT       port on 127.0.0.1, required
#
# Exit status: that of the gateway; 1 for a missing setting, no wallet, or a failed build.
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${FABRIC_DIR}"
# shellcheck source=lib/gateway-run.sh
source "${FABRIC_DIR}/lib/gateway-run.sh"

SERVE_NAME=saam-medtrace-gateway-serve

main() {
  local token_dir=${GATEWAY_SERVE_TOKEN_DIR:-} port=${GATEWAY_SERVE_PORT:-}
  [[ -n "${token_dir}" ]] || unavailable "GATEWAY_SERVE_TOKEN_DIR is required."
  [[ "${port}" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) \
    || unavailable "GATEWAY_SERVE_PORT must be a port between 1024 and 65535."
  [[ -f "${token_dir}/tokens.json" ]] || unavailable "no tokens.json in GATEWAY_SERVE_TOKEN_DIR."

  # Host Node reads the file where it is; the container reads it from a read-only mount.
  export AGENT_TOKEN_FILE="${token_dir}/tokens.json"
  export GATEWAY_PORT="${port}"
  run_gateway_script start \
    --name "${SERVE_NAME}" \
    -p "127.0.0.1:${port}:8080" \
    -v "${token_dir}:/tokens:ro" \
    -e AGENT_TOKEN_FILE=/tokens/tokens.json \
    -e GATEWAY_HOST=0.0.0.0 \
    -e GATEWAY_PORT=8080
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
