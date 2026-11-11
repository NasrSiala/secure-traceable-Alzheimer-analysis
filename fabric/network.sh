#!/usr/bin/env bash
# Lifecycle for the isolated SAAMSTIAHF Fabric test network.
#
#   fabric/network.sh start|up
#   fabric/network.sh status
#   fabric/network.sh stop|down
#
# Docker project, containers, volumes, and the network are named
# saam-medtrace. stop removes only those resources.
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=saam-medtrace
CHANNEL=medtrace
PEER_IMAGE=hyperledger/fabric-peer:2.5.16
ORDERER_IMAGE=hyperledger/fabric-orderer:2.5.16
CA_IMAGE=hyperledger/fabric-ca:1.5.17
TOOLS_IMAGE=hyperledger/fabric-tools:2.5.16
HOST_PORTS=(18050 18051 18052 18053 18054 18055 18056)
CONTAINERS=(
  saam-medtrace-ca-org1
  saam-medtrace-ca-org2
  saam-medtrace-ca-orderer
  saam-medtrace-orderer
  saam-medtrace-peer0-org1
  saam-medtrace-peer0-org2
)
VOLUMES=(
  saam-medtrace-orderer-ledger
  saam-medtrace-peer0-org1-ledger
  saam-medtrace-peer0-org2-ledger
)

cd "${FABRIC_DIR}"

die() {
  echo "error: $*" >&2
  dump_logs
  exit 1
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    die "Docker is required but was not found on PATH."
  fi
  if ! docker info >/dev/null 2>&1; then
    die "Docker is installed but the daemon is not reachable."
  fi
  if ! docker compose version >/dev/null 2>&1; then
    die "Docker Compose v2 is required (the 'docker compose' command)."
  fi
}

compose() {
  local args=(--project-name "${PROJECT}" -f compose/compose.yaml)
  if [[ -f .runtime/ca.env ]]; then
    args+=(--env-file .runtime/ca.env)
  fi
  docker compose "${args[@]}" "$@"
}

dump_logs() {
  command -v docker >/dev/null 2>&1 || return 0
  docker info >/dev/null 2>&1 || return 0
  local name
  for name in "${CONTAINERS[@]}"; do
    if docker inspect "${name}" >/dev/null 2>&1; then
      echo "----- logs ${name} -----" >&2
      docker logs --tail 40 "${name}" >&2 || true
    fi
  done
}

ensure_image() {
  local image=$1
  if docker image inspect "${image}" >/dev/null 2>&1; then
    return 0
  fi
  echo "Pulling ${image}"
  docker pull "${image}" || die "Could not pull ${image}."
}

# The two helpers below (port probe, secret generation) need any Python 3.
# Override the interpreter with PYTHON=/path/to/python.
PY=()

resolve_python() {
  if [[ ${#PY[@]} -gt 0 ]]; then
    return 0
  fi
  local probe='import secrets, socket, sys; sys.exit(0 if sys.version_info[0] == 3 else 1)'
  local candidate
  if [[ -n "${PYTHON:-}" ]]; then
    if "${PYTHON}" -c "${probe}" >/dev/null 2>&1; then
      PY=("${PYTHON}")
      return 0
    fi
    die "PYTHON=${PYTHON} is not a working Python 3 interpreter."
  fi
  for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c "${probe}" >/dev/null 2>&1; then
      PY=("${candidate}")
      return 0
    fi
  done
  if command -v py >/dev/null 2>&1 && py -3 -c "${probe}" >/dev/null 2>&1; then
    PY=(py -3)
    return 0
  fi
  die "Python 3 is required (tried python3, python, py -3). Install it or set PYTHON=/path/to/python."
}

# Exit status 3 from the probe means "a port is busy"; anything else is a tooling failure.
check_ports() {
  resolve_python
  local status=0
  "${PY[@]}" - "${HOST_PORTS[@]}" <<'PY' || status=$?
import socket
import sys

busy = []
for port in (int(arg) for arg in sys.argv[1:]):
    sock = socket.socket()
    sock.settimeout(0.3)
    try:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            busy.append(port)
    finally:
        sock.close()
if busy:
    print(
        "Host ports already in use: " + ", ".join(str(port) for port in busy),
        file=sys.stderr,
    )
    print("saam-medtrace will not stop the process using them.", file=sys.stderr)
    sys.exit(3)
PY
  case "${status}" in
    0) ;;
    3) die "Refusing to start because a required host port is already in use." ;;
    *) die "The host port check failed unexpectedly (exit ${status})." ;;
  esac
}

# .runtime/ca.env holds every CA bootstrap and enrolment password: owner-only.
write_secrets() {
  resolve_python
  mkdir -p .runtime
  (
    umask 077
    "${PY[@]}" - <<'PY'
import secrets

keys = [
    "CA_ORG1_PASSWORD",
    "CA_ORG2_PASSWORD",
    "CA_ORDERER_PASSWORD",
    "PEER_ORG1_PASSWORD",
    "PEER_ORG2_PASSWORD",
    "ORG1_ADMIN_PASSWORD",
    "ORG2_ADMIN_PASSWORD",
    "ORDERER_PASSWORD",
    "ORDERER_ADMIN_PASSWORD",
]
lines = [
    "CA_ORG1_USER=admin",
    "CA_ORG2_USER=admin",
    "CA_ORDERER_USER=admin",
]
lines.extend(f"{key}={secrets.token_hex(16)}" for key in keys)
with open(".runtime/ca.env", "w", encoding="utf-8", newline="\n") as handle:
    handle.write("\n".join(lines) + "\n")
PY
  )
  chmod 600 .runtime/ca.env
}

wait_for_file() {
  local path=$1
  local attempts=$2
  local try
  for ((try = 1; try <= attempts; try++)); do
    if [[ -s "${path}" ]]; then
      return 0
    fi
    sleep 2
  done
  die "Timed out waiting for ${path}."
}

wait_running() {
  local name=$1
  local attempts=$2
  local try state
  for ((try = 1; try <= attempts; try++)); do
    state=$(docker inspect -f '{{.State.Status}}' "${name}" 2>/dev/null || true)
    if [[ "${state}" == "running" ]]; then
      return 0
    fi
    if [[ "${state}" == "exited" || "${state}" == "dead" ]]; then
      docker logs --tail 40 "${name}" >&2 || true
      die "${name} exited before it became ready."
    fi
    sleep 2
  done
  die "${name} did not start."
}

container_running() {
  local name=$1
  local state
  state=$(docker inspect -f '{{.State.Running}}' "${name}" 2>/dev/null || true)
  [[ "${state}" == "true" ]]
}

cmd_status() {
  require_docker
  local healthy=1
  local name listed database

  echo "project: ${PROJECT}"
  echo "channel: ${CHANNEL}"
  echo "state_database: goleveldb"
  echo "fabric_peer: 2.5.16"
  echo "fabric_orderer: 2.5.16"
  echo "fabric_ca: 1.5.17"

  for name in "${CONTAINERS[@]}"; do
    if container_running "${name}"; then
      echo "container ${name}: running"
    else
      echo "container ${name}: absent"
      healthy=0
    fi
  done

  for name in saam-medtrace-peer0-org1 saam-medtrace-peer0-org2; do
    database=$(docker exec "${name}" printenv CORE_LEDGER_STATE_STATEDATABASE 2>/dev/null || true)
    if [[ "${database}" == "goleveldb" ]]; then
      echo "${name} state_database: goleveldb"
    else
      echo "${name} state_database: missing"
      healthy=0
    fi
    listed=$(docker exec "${name}" peer channel list 2>/dev/null || true)
    if channel_listed "${listed}"; then
      echo "${name}: joined"
    else
      echo "${name}: not-joined"
      healthy=0
    fi
  done

  # osnadmin ships in fabric-tools, not in the orderer image. Only ask an orderer
  # that is running: `compose run` on a stopped project would create the Docker
  # network and the bind-mount directories (status must not change anything).
  listed=""
  if container_running saam-medtrace-orderer; then
    listed=$(compose --profile tools run -T --rm --no-deps tools -lc \
      "osnadmin channel list -o orderer.example.com:7053 --ca-file /work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/ca.crt --client-cert /work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt --client-key /work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key" \
      2>/dev/null || true)
  fi
  if orderer_lists_channel "${listed}"; then
    echo "orderer: joined"
  else
    echo "orderer: not-joined"
    healthy=0
  fi

  if [[ "${healthy}" -eq 1 ]]; then
    echo "state: healthy"
    return 0
  fi
  echo "state: unhealthy"
  return 1
}

assert_fabric_dir() {
  case "${PWD}" in
    */fabric) ;;
    *) die "Refusing to delete because the working directory is not fabric/." ;;
  esac
}

remove_generated() {
  assert_fabric_dir
  local target try
  for target in organizations channel-artifacts .runtime; do
    if [[ ! -e "${target}" ]]; then
      continue
    fi
    for ((try = 1; try <= 5; try++)); do
      if rm -rf "${target}"; then
        break
      fi
      sleep 1
    done
    if [[ -e "${target}" ]]; then
      die "Could not remove ${PWD}/${target}."
    fi
  done
}

remove_labeled_containers() {
  local ids
  ids=$(docker ps -aq --filter label=saam.network=medtrace)
  if [[ -n "${ids}" ]]; then
    # shellcheck disable=SC2086
    docker rm -f ${ids} >/dev/null
  fi
}

volume_label() {
  local volume="$1"
  docker volume inspect -f '{{if .Labels}}{{index .Labels "saam.network"}}{{end}}' "${volume}" 2>/dev/null || true
}

refuse_unlabeled_volumes() {
  local volume label
  for volume in "${VOLUMES[@]}"; do
    if ! docker volume inspect "${volume}" >/dev/null 2>&1; then
      continue
    fi
    label=$(volume_label "${volume}")
    if [[ "${label}" != "medtrace" ]]; then
      die "Volume ${volume} exists but is not labeled saam.network=medtrace. It was not removed."
    fi
  done
}

remove_known_volumes() {
  local volume
  refuse_unlabeled_volumes
  for volume in "${VOLUMES[@]}"; do
    if docker volume inspect "${volume}" >/dev/null 2>&1; then
      docker volume rm "${volume}" >/dev/null
    fi
  done
}

remove_project_network() {
  if ! docker network inspect "${PROJECT}" >/dev/null 2>&1; then
    return 0
  fi
  local names name
  names=$(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "${PROJECT}")
  for name in ${names}; do
    name=${name#/}
    if [[ "${name}" != ${PROJECT}-* ]]; then
      die "Network ${PROJECT} is attached to unexpected container ${name}. It was not removed."
    fi
  done
  remove_labeled_containers
  docker network rm "${PROJECT}" >/dev/null
}

channel_listed() {
  local listed="$1" line
  while IFS= read -r line; do
    if [[ "${line}" == "${CHANNEL}" ]]; then
      return 0
    fi
  done <<<"${listed}"
  return 1
}

orderer_lists_channel() {
  local listed="$1"
  [[ "${listed}" == *"\"name\":\"${CHANNEL}\""* || "${listed}" == *"\"name\": \"${CHANNEL}\""* ]]
}

cmd_stop() {
  require_docker
  assert_fabric_dir
  refuse_unlabeled_volumes
  compose down --volumes --remove-orphans >/dev/null
  remove_labeled_containers
  remove_known_volumes
  remove_project_network
  remove_generated
  echo "state: stopped"
  echo "project: ${PROJECT}"
}

prepare_dirs() {
  mkdir -p \
    organizations/fabric-ca/org1 \
    organizations/fabric-ca/org2 \
    organizations/fabric-ca/ordererOrg \
    channel-artifacts \
    .runtime
}

cmd_start() {
  require_docker
  if cmd_status >/dev/null 2>&1; then
    echo "saam-medtrace is already healthy"
    cmd_status
    return 0
  fi

  echo "Removing any leftover saam-medtrace resources"
  cmd_stop >/dev/null

  ensure_image "${CA_IMAGE}"
  ensure_image "${ORDERER_IMAGE}"
  ensure_image "${PEER_IMAGE}"
  ensure_image "${TOOLS_IMAGE}"
  check_ports
  prepare_dirs
  write_secrets

  echo "Starting certificate authorities"
  compose up -d ca-org1 ca-org2 ca-orderer
  wait_running saam-medtrace-ca-org1 30
  wait_running saam-medtrace-ca-org2 30
  wait_running saam-medtrace-ca-orderer 30
  wait_for_file organizations/fabric-ca/org1/ca-cert.pem 30
  wait_for_file organizations/fabric-ca/org2/ca-cert.pem 30
  wait_for_file organizations/fabric-ca/ordererOrg/ca-cert.pem 30

  echo "Enrolling network identities"
  compose --profile tools run -T --rm --no-deps ca-client /work/scripts/enroll.sh
  echo "Creating channel ${CHANNEL}"
  compose --profile tools run -T --rm --no-deps tools -lc \
    "mkdir -p /work/channel-artifacts && configtxgen -profile ChannelUsingRaft -outputBlock /work/channel-artifacts/${CHANNEL}.block -channelID ${CHANNEL}"
  if [[ ! -s channel-artifacts/${CHANNEL}.block ]]; then
    die "configtxgen did not write channel-artifacts/${CHANNEL}.block."
  fi

  echo "Starting orderer and peers"
  docker run --rm --entrypoint cat "${PEER_IMAGE}" /etc/hyperledger/fabric/core.yaml > .runtime/core.yaml
  if [[ ! -s .runtime/core.yaml ]]; then
    die "Could not read core.yaml from ${PEER_IMAGE}."
  fi
  compose up -d orderer peer0-org1 peer0-org2
  wait_running saam-medtrace-orderer 30
  wait_running saam-medtrace-peer0-org1 30
  wait_running saam-medtrace-peer0-org2 30

  local try listed
  for ((try = 1; try <= 30; try++)); do
    if docker exec saam-medtrace-peer0-org1 peer channel list >/dev/null 2>&1 \
      && docker exec saam-medtrace-peer0-org2 peer channel list >/dev/null 2>&1; then
      break
    fi
    if [[ "${try}" -eq 30 ]]; then
      die "Peers did not accept CLI commands."
    fi
    sleep 2
  done

  echo "Joining channel ${CHANNEL}"
  compose --profile tools run -T --rm --no-deps tools /work/scripts/join-channel.sh

  cmd_status
}

usage() {
  cat <<'EOF'
Usage: fabric/network.sh <start|status|stop>

  start, up     Start Org1, Org2, the Raft orderer, their CAs, and channel medtrace
  status        Print health and exit 0 only when the network is healthy
  stop, down    Stop the network and remove its containers, volumes, and generated files

Org1 is the platform organization and Org2 is the audit organization.
State database: LevelDB. Docker project: saam-medtrace.
Generated certificates and bootstrap secrets stay under fabric/organizations,
fabric/channel-artifacts, and fabric/.runtime, which are gitignored.
EOF
}

main() {
  local command=${1:-}
  case "${command}" in
    start|up)
      cmd_start
      ;;
    status)
      cmd_status
      ;;
    stop|down)
      cmd_stop
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      usage >&2
      echo "error: Unknown command: ${command}" >&2
      exit 2
      ;;
  esac
}

# Run only when executed; `source fabric/network.sh` exposes the functions to tests.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
