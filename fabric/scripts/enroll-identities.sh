#!/usr/bin/env bash
# Register and enroll the nine Fabric identities. Passwords come from the
# gitignored runtime file. Nothing secret is written to stdout.
set -euo pipefail

cd /work

if [[ ! -f /work/runtime/ca.env || ! -f /work/runtime/identities.env ]]; then
  echo "Missing CA or identity runtime files. Run fabric/enroll-identities.sh from the host." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source /work/runtime/ca.env
# shellcheck disable=SC1091
source /work/runtime/identities.env
set +a

copy_one() {
  local pattern=$1
  local dest=$2
  local matches=()
  shopt -s nullglob
  # shellcheck disable=SC2206
  matches=(${pattern})
  shopt -u nullglob
  if [[ ${#matches[@]} -ne 1 ]]; then
    echo "Expected one file matching ${pattern}, found ${#matches[@]}." >&2
    exit 1
  fi
  cp "${matches[0]}" "${dest}"
}

sanitize() {
  printf '%s\n' "$1" | sed -E \
    -e 's#https://[^@[:space:]]+@#https://[redacted]@#g' \
    -e 's/[0-9a-fA-F]{32}/[redacted]/g'
}

register_identity() {
  local home=$1
  local ca_name=$2
  local ca_cert=$3
  local name=$4
  local secret=$5
  secret=${secret//$'\r'/}
  shift 5
  local output
  export FABRIC_CA_CLIENT_HOME="${home}"
  if output=$(fabric-ca-client register \
    --caname "${ca_name}" \
    --id.name "${name}" \
    --id.secret "${secret}" \
    --id.type client \
    "$@" \
    --tls.certfiles "${ca_cert}" 2>&1); then
    return 0
  fi
  if [[ "${output}" == *"already registered"* ]]; then
    return 0
  fi
  echo "Could not register ${name}." >&2
  sanitize "${output}" >&2
  exit 1
}

# This container runs as root. On Linux the host user must still read its own wallet (the
# tests, `npm run spike:submit`) and delete it on `stop`: give the files to the owner of
# /work/wallet, which the host created. Where the mount maps every file to root (Docker
# Desktop) that owner is 0:0 and nothing changes.
hand_to_wallet_owner() {
  local owner
  owner=$(stat -c '%u:%g' /work/wallet)
  if [[ "${owner}" != "0:0" ]]; then
    chown -R "${owner}" "$1"
  fi
}

enroll_client() {
  local ca_host=$1
  local ca_port=$2
  local ca_name=$3
  local ca_cert=$4
  local name=$5
  local secret=$6
  secret=${secret//$'\r'/}
  local domain=$7
  local mspid=$8
  shift 8
  local org_home="/work/organizations/peerOrganizations/${domain}"
  local msp="${org_home}/users/${name}@${domain}/msp"
  export FABRIC_CA_CLIENT_HOME="${org_home}"
  # Every enrollment adds a new private key to keystore/. Start from an empty MSP
  # directory so this script can be run again on a live network (copy_one below
  # expects exactly one key and one certificate).
  if [[ -z "${name}" || -z "${domain}" ]]; then
    echo "enroll_client needs an identity name and a domain." >&2
    exit 1
  fi
  rm -rf -- "${msp}"
  echo "Enrolling ${name}"
  local output
  if ! output=$(fabric-ca-client enroll \
    -u "https://${name}:${secret}@${ca_host}:${ca_port}" \
    --caname "${ca_name}" \
    -M "${msp}" \
    "$@" \
    --tls.certfiles "${ca_cert}" 2>&1); then
    echo "Could not enroll ${name}." >&2
    sanitize "${output}" >&2
    exit 1
  fi
  local wallet="/work/wallet/${name}"
  mkdir -p "${wallet}"
  copy_one "${msp}/signcerts/*" "${wallet}/cert.pem"
  copy_one "${msp}/keystore/*" "${wallet}/key.pem"
  printf '%s\n' "${mspid}" > "${wallet}/msp-id"
  chmod 600 "${wallet}/cert.pem" "${wallet}/key.pem" || true
  hand_to_wallet_owner "${wallet}"
}

enroll_org1_agent() {
  local short_name=$1
  local secret_var="AGENT_$(printf '%s' "${short_name}" | tr '[:lower:]' '[:upper:]')_PASSWORD"
  local secret="${!secret_var}"
  secret=${secret//$'\r'/}
  local ca_cert="/work/organizations/fabric-ca/org1/ca-cert.pem"
  local home="/work/organizations/peerOrganizations/org1.example.com"
  local identity="agent-${short_name}"
  register_identity "${home}" ca-org1 "${ca_cert}" "${identity}" "${secret}" \
    --id.attrs "role=pipeline-agent:ecert,agent=${short_name}:ecert"
  enroll_client ca-org1 7054 ca-org1 "${ca_cert}" "${identity}" "${secret}" \
    org1.example.com Org1MSP \
    --enrollment.attrs "role,agent"
}

org1_cert=/work/organizations/fabric-ca/org1/ca-cert.pem
org2_cert=/work/organizations/fabric-ca/org2/ca-cert.pem

for agent in ingestion preparation features prediction validation explanation finalization; do
  enroll_org1_agent "${agent}"
done

register_identity /work/organizations/peerOrganizations/org1.example.com \
  ca-org1 "${org1_cert}" model-admin "${MODEL_ADMIN_PASSWORD}" \
  --id.attrs "role=model-admin:ecert"
enroll_client ca-org1 7054 ca-org1 "${org1_cert}" model-admin "${MODEL_ADMIN_PASSWORD}" \
  org1.example.com Org1MSP \
  --enrollment.attrs "role"

register_identity /work/organizations/peerOrganizations/org2.example.com \
  ca-org2 "${org2_cert}" verifier "${VERIFIER_PASSWORD}"
enroll_client ca-org2 7054 ca-org2 "${org2_cert}" verifier "${VERIFIER_PASSWORD}" \
  org2.example.com Org2MSP

# The gateway also needs the peer's TLS CA certificate. It is public, but on Linux
# organizations/ is readable by root only, so publish it next to the identities.
tls_ca=/work/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
cp "${tls_ca}" /work/wallet/peer0-org1-tls-ca.crt
chmod 644 /work/wallet/peer0-org1-tls-ca.crt
hand_to_wallet_owner /work/wallet/peer0-org1-tls-ca.crt

echo "Identity enrollment complete"
