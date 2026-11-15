#!/usr/bin/env bash
# Run the seven-artifact history check (T2.5a). It compiles first, so it always checks the
# sources you have. Uses host Node when it can build, otherwise the spike image. Exit status:
#   0  GetCaseHistory returned the chain in parent-to-child order, and the other checks held
#   1  a wrong answer, no wallet, or a failed build
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${FABRIC_DIR}"
# shellcheck source=lib/gateway-run.sh
source "${FABRIC_DIR}/lib/gateway-run.sh"

main() {
  run_gateway_script check:history
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
