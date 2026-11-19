#!/usr/bin/env bash
# Audit helper: one fresh test network, the four live checks, then stop it. Log: audit/round-7/live.log
set -uo pipefail
cd "$(dirname "$0")/../../.."
LOG=audit/round-7/live.log
: > "${LOG}"
step() {
  local started=$SECONDS
  echo "=== $* (start)" >> "${LOG}"
  "$@" >> "${LOG}" 2>&1
  local code=$?
  echo "=== $* -> exit ${code} in $((SECONDS - started)) s" >> "${LOG}"
  return ${code}
}
cleanup() { step bash fabric/network.sh stop; echo "DONE" >> "${LOG}"; }
trap cleanup EXIT
step bash fabric/network.sh start || exit 1
step bash fabric/enroll-identities.sh || exit 1
step bash fabric/gateway-check.sh
step bash fabric/history-check.sh
step bash fabric/model-check.sh
step bash fabric/gateway-routes-check.sh
step bash fabric/gateway-routes-check.sh
