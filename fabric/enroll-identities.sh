#!/usr/bin/env bash
# Enroll the nine agent identities and deploy the attribute-reading demo chaincode.
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

FABRIC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=saam-medtrace
cd "${FABRIC_DIR}"

die() {
  echo "error: $*" >&2
  exit 1
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker is required but was not found on PATH."
  docker info >/dev/null 2>&1 || die "Docker is installed but the daemon is not reachable."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."
}

compose_tools() {
  docker compose --project-name "${PROJECT}" --env-file .runtime/ca.env \
    -f compose/compose.yaml --profile tools "$@"
}

compose_spike() {
  local args=(--project-name "${PROJECT}" --env-file .runtime/ca.env)
  if [[ -f .runtime/cc.env ]]; then
    args+=(--env-file .runtime/cc.env)
  fi
  docker compose "${args[@]}" -f compose/compose.yaml --profile spike "$@"
}

resolve_python() {
  local probe='import secrets, sys; sys.exit(0 if sys.version_info[0] == 3 else 1)'
  if [[ -n "${PYTHON:-}" ]] && "${PYTHON}" -c "${probe}" >/dev/null 2>&1; then
    PY=("${PYTHON}")
    return 0
  fi
  local candidate
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
  die "Python 3 is required to enroll identities."
}

write_identity_secrets() {
  if [[ -f .runtime/identities.env ]]; then
    return 0
  fi
  resolve_python
  umask 077
  "${PY[@]}" - <<'PY'
import secrets
from pathlib import Path

names = [
    "AGENT_INGESTION_PASSWORD",
    "AGENT_PREPARATION_PASSWORD",
    "AGENT_FEATURES_PASSWORD",
    "AGENT_PREDICTION_PASSWORD",
    "AGENT_VALIDATION_PASSWORD",
    "AGENT_EXPLANATION_PASSWORD",
    "AGENT_FINALIZATION_PASSWORD",
    "VERIFIER_PASSWORD",
    "MODEL_ADMIN_PASSWORD",
]
lines = [f"{name}={secrets.token_hex(16)}" for name in names]
with open(".runtime/identities.env", "w", encoding="utf-8", newline="\n") as handle:
    handle.write("\n".join(lines) + "\n")
PY
  chmod 600 .runtime/identities.env || true
}

peers_have_builder() {
  docker exec saam-medtrace-peer0-org1 test -x /opt/hyperledger/ccaas_builder/bin/detect \
    && docker exec saam-medtrace-peer0-org2 test -x /opt/hyperledger/ccaas_builder/bin/detect
}

build_node_package() {
  local service=$1
  local label=$2
  echo "Building ${label}"
  # `npm ci` installs exactly what the committed package-lock.json says and fails
  # when it disagrees with package.json; --ignore-scripts keeps dependency install
  # scripts out of a container that sits on the Fabric network.
  # The container runs as root. On Linux, hand node_modules and dist back to the owner of
  # the checkout (0:0 under Docker Desktop: nothing to do); otherwise the host user could
  # neither run npm nor delete them afterwards.
  local script='npm ci --ignore-scripts && npm run build && owner=$(stat -c %u:%g .) && { [ "${owner}" = 0:0 ] || chown -R "${owner}" node_modules dist; }'
  compose_spike run -T --rm --no-deps "${service}" -lc "${script}" \
    || die "Could not build ${label}. The Node 20 image and npm registry must be reachable, and package-lock.json must match package.json."
}

write_chaincode_packages() {
  resolve_python
  "${PY[@]}" - <<'PY'
import gzip
import io
import json
import tarfile
from pathlib import Path


def tgz(members):
    """Reproducible .tgz: no timestamp or file name in the gzip header and the
    default (zero) tar metadata, so the same inputs give the same bytes and the
    same chaincode package identifier on every run."""
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, data in members:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return raw.getvalue()


root = Path(".runtime/cc")
root.mkdir(parents=True, exist_ok=True)
packages = {
    "org1": "saam-medtrace-cc-org1:9999",
    "org2": "saam-medtrace-cc-org2:9999",
}
for org, address in packages.items():
    connection = json.dumps(
        {"address": address, "dial_timeout": "120s", "tls_required": False},
        separators=(",", ":"),
    ).encode()
    metadata = json.dumps(
        {"type": "ccaas", "label": "provenance"},
        separators=(",", ":"),
    ).encode()
    code = tgz([("connection.json", connection)])
    (root / f"{org}.tgz").write_bytes(
        tgz([("code.tar.gz", code), ("metadata.json", metadata)])
    )
PY
}

wait_for_chaincode() {
  local peer host attempt
  echo "Waiting for chaincode servers"
  for pair in "saam-medtrace-peer0-org1 saam-medtrace-cc-org1" "saam-medtrace-peer0-org2 saam-medtrace-cc-org2"; do
    peer=${pair%% *}
    host=${pair##* }
    attempt=1
    while [[ "${attempt}" -le 60 ]]; do
      if docker exec "${peer}" bash -c "echo >/dev/tcp/${host}/9999" >/dev/null 2>&1; then
        break
      fi
      if ! docker inspect -f '{{.State.Running}}' "${host}" 2>/dev/null | grep -q true; then
        docker logs --tail 80 "${host}" >&2 || true
        die "Chaincode container ${host} stopped before it accepted connections."
      fi
      if [[ "${attempt}" -eq 60 ]]; then
        docker logs --tail 80 "${host}" >&2 || true
        die "Chaincode server ${host} did not accept connections."
      fi
      attempt=$((attempt + 1))
      sleep 2
    done
  done
}

deploy_chaincode() {
  write_chaincode_packages
  echo "Installing provenance on both peers"
  local output
  if ! output=$(bash ./deploy-chaincode.sh); then
    die "Chaincode deployment failed."
  fi
  # grep finds nothing when the script printed no identifiers; do not let pipefail
  # end the script silently before the explicit check below reports it.
  printf '%s\n' "${output}" | tr -d '\r' | grep '^PACKAGE_ORG' > .runtime/cc.env || true
  chmod 600 .runtime/cc.env || true
  if ! grep -q '^PACKAGE_ORG1=provenance:' .runtime/cc.env \
    || ! grep -q '^PACKAGE_ORG2=provenance:' .runtime/cc.env; then
    die "Chaincode deployment did not return both package identifiers."
  fi
  # Compose reads CHAINCODE_ID_ORG1, while the peer CLI reports PACKAGE_ORG1.
  sed 's/^PACKAGE_ORG/CHAINCODE_ID_ORG/' .runtime/cc.env > .runtime/cc.compose.env
  mv .runtime/cc.compose.env .runtime/cc.env
  docker rm -f saam-medtrace-cc-org1 saam-medtrace-cc-org2 >/dev/null 2>&1 || true
  echo "Starting chaincode services"
  compose_spike up -d cc-org1 cc-org2
  wait_for_chaincode
}

cmd_enroll() {
  require_docker
  mkdir -p wallet .runtime
  if ! peers_have_builder; then
    echo "Restarting medtrace so the peers load the chaincode builder."
    bash ./network.sh stop
    bash ./network.sh start
  fi
  bash ./network.sh status >/dev/null || die "The medtrace network is not healthy."
  write_identity_secrets
  echo "Enrolling nine identities"
  compose_tools run -T --rm --no-deps ca-client /work/scripts/enroll-identities.sh
  build_node_package cc-build "provenance chaincode"
  build_node_package gw-build "ledger gateway"
  deploy_chaincode
  echo "Identities enrolled and provenance is ready"
}

cmd_enroll
