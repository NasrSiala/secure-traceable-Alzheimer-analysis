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
# shellcheck source=lib/gateway-run.sh
source "${FABRIC_DIR}/lib/gateway-run.sh"

export GATEWAY_SCENARIO="${GATEWAY_SCENARIO:-flow}"

main() {
  run_gateway_script check:gateway -e GATEWAY_SCENARIO
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
