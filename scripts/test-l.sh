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

The TypeScript packages (chaincode/provenance, ledger-gateway) are type-checked
with the host's Node, or else inside the pinned Node image of
fabric/compose/compose.yaml when Docker is running. With neither, the script
fails (exit 3). SAAM_TEST_SKIP_NODE=1 skips that check knowingly; it is then
reported as SKIPPED.
EOF
}

select_pytest() {
  if [[ -f pyproject.toml ]] && command -v uv >/dev/null 2>&1; then
    PYTEST=(uv run pytest)
    return 0
  fi
  # Same order as fabric/network.sh: python3 is the only name on stock Ubuntu,
  # python is the usual name on Windows, `py -3` is the Windows launcher.
  local candidate
  for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c "import pytest" >/dev/null 2>&1; then
      PYTEST=("${candidate}" -m pytest)
      return 0
    fi
  done
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

# The Node image the Compose services use, so the TypeScript check and the
# enrollment build run on the same pinned runtime.
node_image() {
  sed -n 's/^[[:space:]]*image:[[:space:]]*\(node:[^[:space:]]*\)[[:space:]]*$/\1/p' \
    "${ROOT}/fabric/compose/compose.yaml" | head -n 1
}

# Absolute path of a directory in the form Docker expects: C:/... under Git Bash
# on Windows (pwd -W), the plain path elsewhere.
host_dir() {
  if (cd "$1" && pwd -W) 2>/dev/null; then
    return 0
  fi
  (cd "$1" && pwd)
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

node_available() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1
}

# Type-check one TypeScript package: with the host's Node when there is one, else
# inside the pinned Node image (source mounted read-only, copied aside, so nothing
# is written to the checkout). With neither, fail: a green run must not mean
# "TypeScript was never looked at". SAAM_TEST_SKIP_NODE=1 is the explicit opt-out.
run_npm_test() {
  local dir=$1
  if [[ ! -f "${dir}/package.json" ]]; then
    return 0
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "npm: ${dir} test"
    return 0
  fi
  if node_available; then
    # A fresh clone has no node_modules. Install exactly what the lockfile says.
    if [[ ! -d "${dir}/node_modules" ]]; then
      echo "${dir}: installing dependencies (npm ci --ignore-scripts)."
      (cd "${dir}" && npm ci --ignore-scripts)
    fi
    (cd "${dir}" && npm test)
    return 0
  fi
  if docker_available; then
    local image
    image=$(node_image)
    if [[ -z "${image}" ]]; then
      echo "error: no node image found in fabric/compose/compose.yaml." >&2
      exit 3
    fi
    echo "${dir}: node is not on PATH; running npm test in ${image}."
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' docker run --rm \
      --label saam.network=medtrace \
      -v "$(host_dir "${dir}"):/src:ro" "${image}" \
      bash -c 'set -e; mkdir /tmp/w; cd /src; tar --exclude=./node_modules --exclude=./dist -cf - . | tar -xf - -C /tmp/w; cd /tmp/w; npm ci --ignore-scripts --no-fund --no-audit; npm test'
    return 0
  fi
  if [[ "${SAAM_TEST_SKIP_NODE:-}" == "1" ]]; then
    echo "SKIPPED: ${dir} npm test (SAAM_TEST_SKIP_NODE=1)."
    return 0
  fi
  echo "error: ${dir} needs Node 20 or a running Docker daemon for its TypeScript check." >&2
  echo "Install Node, start Docker, or set SAAM_TEST_SKIP_NODE=1 to skip it knowingly." >&2
  exit 3
}

run_local() {
  echo "Running the local suite (fabric and board excluded)."
  run_pytest -q -o addopts= -m "not fabric and not board" tests
  run_npm_test chaincode/provenance
  run_npm_test ledger-gateway
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

main() {
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
}

# Run only when executed; `source scripts/test-l.sh` loads the functions for tests.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
