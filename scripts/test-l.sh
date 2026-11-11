#!/usr/bin/env bash
# L-role test entry point. Fabric and board tests stay opt-in.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${ROOT}"

FABRIC=0
BOARD=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/test-l.sh [--fabric] [--board] [--dry-run]

  (no flag)   Local tests that do not need Fabric or the Zybo board
  --fabric    Also run tests marked fabric (requires Docker)
  --board     Also run tests marked board (requires the Zybo Z7-10)
  --dry-run   Print the selected commands without running them

--fabric --board runs the local suite plus both optional suites.
Board mode never opens a serial device itself. It only selects pytest tests
marked board, and exits successfully when none are registered yet.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fabric)
      FABRIC=1
      ;;
    --board)
      BOARD=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

export PYTEST_ADDOPTS=

select_pytest() {
  if [[ -f pyproject.toml ]] && command -v uv >/dev/null 2>&1; then
    PYTEST=(uv run pytest)
    return 0
  fi
  if command -v python >/dev/null 2>&1 && python -c "import pytest" >/dev/null 2>&1; then
    PYTEST=(python -m pytest)
    return 0
  fi
  if command -v py >/dev/null 2>&1 && py -3 -c "import pytest" >/dev/null 2>&1; then
    PYTEST=(py -3 -m pytest)
    return 0
  fi
  echo "pytest is not available. Install it, or add the project pyproject.toml so uv can run it." >&2
  exit 3
}

run_pytest() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "pytest-args: $*"
    return 0
  fi
  "${PYTEST[@]}" "$@"
}

require_docker_for_fabric() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "fabric-prerequisite: docker"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "Fabric tests need a running Docker daemon. Start Docker and retry scripts/test-l.sh --fabric." >&2
    exit 3
  fi
}

run_local() {
  echo "Running the local suite (fabric and board excluded)."
  run_pytest -q -o addopts= -m "not fabric and not board" tests
  if [[ -f chaincode/provenance/package.json ]]; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      echo "npm: chaincode/provenance test"
    else
      (cd chaincode/provenance && npm test)
    fi
  fi
  if [[ -f ledger-gateway/package.json ]]; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      echo "npm: ledger-gateway test"
    else
      (cd ledger-gateway && npm test)
    fi
  fi
  if [[ -f hw/sim/Makefile ]]; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      echo "make: hw/sim"
    else
      make -C hw/sim
    fi
  fi
  if [[ -d hw/host/tests ]]; then
    run_pytest -q -o addopts= -m "not board" hw/host/tests
  fi
}

run_fabric() {
  require_docker_for_fabric
  echo "Running tests marked fabric."
  run_pytest -q -o addopts= -m fabric tests
}

run_board() {
  local targets=(tests)
  if [[ -d hw/host/tests ]]; then
    targets+=(hw/host/tests)
  fi
  echo "Running tests marked board."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    run_pytest -q -o addopts= -m board "${targets[@]}"
    echo "board-access: no"
    return 0
  fi
  set +e
  "${PYTEST[@]}" -q -o addopts= -m board "${targets[@]}"
  local rc=$?
  set -e
  if [[ "${rc}" -eq 5 ]]; then
    echo "No board tests are registered. The board was not opened."
    echo "board-access: no"
    return 0
  fi
  if [[ "${rc}" -ne 0 ]]; then
    exit "${rc}"
  fi
  echo "board-access: tests-only"
}

select_pytest
if [[ "${DRY_RUN}" -eq 1 ]]; then
  run_local
  if [[ "${FABRIC}" -eq 1 ]]; then
    run_fabric
  fi
  if [[ "${BOARD}" -eq 1 ]]; then
    run_board
  fi
  exit 0
fi

# A test inside the local suite may call this script. Skip the local suite on
# that nested call so the suite cannot invoke itself forever.
if [[ "${SAAM_TEST_L_RUNNING:-}" != "1" ]]; then
  export SAAM_TEST_L_RUNNING=1
  run_local
else
  echo "Nested test-l.sh call: local suite already running."
fi
if [[ "${FABRIC}" -eq 1 ]]; then
  run_fabric
fi
if [[ "${BOARD}" -eq 1 ]]; then
  run_board
fi
