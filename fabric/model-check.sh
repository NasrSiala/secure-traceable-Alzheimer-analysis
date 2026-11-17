#!/usr/bin/env bash
# Run the model registry check (T2.5b). It compiles first, so it always checks the sources you
# have. Uses host Node when it can build, otherwise the spike image. Exit status:
#   0  RegisterModel and GetModel behaved as Schema 5.2 and AC-04.3 say, for the real identities
#   1  a wrong answer, no wallet, or a failed build
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${FABRIC_DIR}"
# shellcheck source=lib/gateway-run.sh
source "${FABRIC_DIR}/lib/gateway-run.sh"

main() {
  run_gateway_script check:model
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
