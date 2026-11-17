#!/usr/bin/env bash
# Seven sequential Fabric transactions (T1.8). Exit status:
#   0  within budget
#   2  measured budget breach (p95 above 7.3 s)
#   1  no baseline: no network or wallet, a failed build, or any other failure
# The script owns this contract: the status of a failed build or of a crashed probe is
# never passed on, because tsc and others also exit with 2.
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# unavailable, and the probes wallet_present, runtime_prepared and host_can_run, which
# tests/scripts/test_spike_latency_script.py replaces.
# shellcheck source=lib/gateway-run.sh
source "${FABRIC_DIR}/lib/gateway-run.sh"

# The container run mounts only ledger-gateway, so the two repository settings the report
# carries are read here and handed over. The probe reads the same files when started alone.
read_settings() {
  local policy_line batch_line
  policy_line=$(grep -E '^POLICY=' "${FABRIC_DIR}/scripts/deploy-chaincode.sh" | head -1 || true)
  ENDORSEMENT_POLICY=${policy_line#POLICY=}
  ENDORSEMENT_POLICY=${ENDORSEMENT_POLICY//$'\r'/}
  ENDORSEMENT_POLICY=${ENDORSEMENT_POLICY#\"}
  ENDORSEMENT_POLICY=${ENDORSEMENT_POLICY%\"}

  batch_line=$(grep -E '^[[:space:]]*BatchTimeout:' "${FABRIC_DIR}/config/configtx.yaml" | head -1 || true)
  BATCH_TIMEOUT=${batch_line##* }
  BATCH_TIMEOUT=${BATCH_TIMEOUT//$'\r'/}

  if [[ -z "${ENDORSEMENT_POLICY}" || -z "${BATCH_TIMEOUT}" ]]; then
    unavailable "BatchTimeout or the endorsement policy was not found."
  fi
  export ENDORSEMENT_POLICY BATCH_TIMEOUT
}

measure_on_host() {
  cd "${FABRIC_DIR}/../ledger-gateway"
  npm run build || unavailable "the TypeScript build failed."
  npm run spike:latency
}

measure_in_container() {
  cd "${FABRIC_DIR}"
  local spike=(docker compose --project-name saam-medtrace --env-file .runtime/ca.env
    -f compose/compose.yaml --profile spike run -T --rm --no-deps --entrypoint npm
    -e ENDORSEMENT_POLICY -e BATCH_TIMEOUT spike)
  "${spike[@]}" run build || unavailable "the TypeScript build failed."
  "${spike[@]}" run spike:latency
}

main() {
  cd "${FABRIC_DIR}"
  wallet_present || unavailable "no wallet. Run fabric/network.sh start, then fabric/enroll-identities.sh."
  read_settings

  local status=0
  if host_can_run; then
    measure_on_host || status=$?
  elif runtime_prepared; then
    measure_in_container || status=$?
  else
    unavailable "Node is not usable here and the Fabric runtime is not prepared."
  fi

  case "${status}" in
    0 | 2) exit "${status}" ;;
    *) unavailable "the measurement ended with exit status ${status}, so there is no baseline." ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
