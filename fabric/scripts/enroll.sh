#!/usr/bin/env bash
# Enroll the bootstrap identities required to run the medtrace network.
# Agent identities are intentionally not created here (increment l02).
set -euo pipefail

cd /work

if [[ ! -f /work/runtime/ca.env ]]; then
  echo "Missing /work/runtime/ca.env." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source /work/runtime/ca.env
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

write_node_ou() {
  local msp_dir=$1
  local certs=()
  shopt -s nullglob
  certs=("${msp_dir}/cacerts/"*.pem)
  shopt -u nullglob
  if [[ ${#certs[@]} -lt 1 ]]; then
    echo "No CA certificate in ${msp_dir}/cacerts." >&2
    exit 1
  fi
  local cert=${certs[0]}
  local rel="cacerts/$(basename "${cert}")"
  cat > "${msp_dir}/config.yaml" <<EOF
NodeOUs:
  Enable: true
  ClientOUIdentifier:
    Certificate: ${rel}
    OrganizationalUnitIdentifier: client
  PeerOUIdentifier:
    Certificate: ${rel}
    OrganizationalUnitIdentifier: peer
  AdminOUIdentifier:
    Certificate: ${rel}
    OrganizationalUnitIdentifier: admin
  OrdererOUIdentifier:
    Certificate: ${rel}
    OrganizationalUnitIdentifier: orderer
EOF
}

enroll_peer_org() {
  local org_key=$1
  local domain=$2
  local ca_host=$3
  local ca_name=$4
  local ca_port=$5
  local ca_dir=$6
  local peer_password=$7
  local admin_password=$8
  local org_home="/work/organizations/peerOrganizations/${domain}"
  local ca_cert="/work/organizations/fabric-ca/${ca_dir}/ca-cert.pem"
  local peer_name="peer0.${domain}"

  echo "Enrolling ${domain}"
  mkdir -p "${org_home}"
  export FABRIC_CA_CLIENT_HOME="${org_home}"

  fabric-ca-client enroll \
    -u "https://admin:${CA_ORG_BOOTSTRAP}@${ca_host}:${ca_port}" \
    --caname "${ca_name}" \
    --tls.certfiles "${ca_cert}"

  write_node_ou "${org_home}/msp"
  mkdir -p "${org_home}/msp/tlscacerts" "${org_home}/tlsca" "${org_home}/ca"
  cp "${ca_cert}" "${org_home}/msp/tlscacerts/ca.crt"
  cp "${ca_cert}" "${org_home}/tlsca/tlsca.${domain}-cert.pem"
  cp "${ca_cert}" "${org_home}/ca/ca.${domain}-cert.pem"

  fabric-ca-client register \
    --caname "${ca_name}" \
    --id.name peer0 \
    --id.secret "${peer_password}" \
    --id.type peer \
    --tls.certfiles "${ca_cert}" >/dev/null

  fabric-ca-client register \
    --caname "${ca_name}" \
    --id.name "${org_key}admin" \
    --id.secret "${admin_password}" \
    --id.type admin \
    --tls.certfiles "${ca_cert}" >/dev/null

  fabric-ca-client enroll \
    -u "https://peer0:${peer_password}@${ca_host}:${ca_port}" \
    --caname "${ca_name}" \
    -M "${org_home}/peers/${peer_name}/msp" \
    --tls.certfiles "${ca_cert}"
  write_node_ou "${org_home}/peers/${peer_name}/msp"

  fabric-ca-client enroll \
    -u "https://peer0:${peer_password}@${ca_host}:${ca_port}" \
    --caname "${ca_name}" \
    -M "${org_home}/peers/${peer_name}/tls" \
    --enrollment.profile tls \
    --csr.hosts "${peer_name}" \
    --csr.hosts localhost \
    --csr.hosts "saam-medtrace-peer0-${org_key}" \
    --tls.certfiles "${ca_cert}"

  copy_one "${org_home}/peers/${peer_name}/tls/tlscacerts/*" "${org_home}/peers/${peer_name}/tls/ca.crt"
  copy_one "${org_home}/peers/${peer_name}/tls/signcerts/*" "${org_home}/peers/${peer_name}/tls/server.crt"
  copy_one "${org_home}/peers/${peer_name}/tls/keystore/*" "${org_home}/peers/${peer_name}/tls/server.key"

  fabric-ca-client enroll \
    -u "https://${org_key}admin:${admin_password}@${ca_host}:${ca_port}" \
    --caname "${ca_name}" \
    -M "${org_home}/users/Admin@${domain}/msp" \
    --tls.certfiles "${ca_cert}"
  write_node_ou "${org_home}/users/Admin@${domain}/msp"
}

enroll_orderer() {
  local org_home="/work/organizations/ordererOrganizations/example.com"
  local ca_cert="/work/organizations/fabric-ca/ordererOrg/ca-cert.pem"
  local orderer_home="${org_home}/orderers/orderer.example.com"

  echo "Enrolling orderer organization"
  mkdir -p "${org_home}"
  export FABRIC_CA_CLIENT_HOME="${org_home}"

  fabric-ca-client enroll \
    -u "https://admin:${CA_ORDERER_PASSWORD}@ca-orderer:7054" \
    --caname ca-orderer \
    --tls.certfiles "${ca_cert}"

  write_node_ou "${org_home}/msp"
  mkdir -p "${org_home}/msp/tlscacerts" "${org_home}/tlsca"
  cp "${ca_cert}" "${org_home}/msp/tlscacerts/tlsca.example.com-cert.pem"
  cp "${ca_cert}" "${org_home}/tlsca/tlsca.example.com-cert.pem"

  fabric-ca-client register \
    --caname ca-orderer \
    --id.name orderer \
    --id.secret "${ORDERER_PASSWORD}" \
    --id.type orderer \
    --tls.certfiles "${ca_cert}" >/dev/null

  fabric-ca-client register \
    --caname ca-orderer \
    --id.name ordererAdmin \
    --id.secret "${ORDERER_ADMIN_PASSWORD}" \
    --id.type admin \
    --tls.certfiles "${ca_cert}" >/dev/null

  fabric-ca-client enroll \
    -u "https://orderer:${ORDERER_PASSWORD}@ca-orderer:7054" \
    --caname ca-orderer \
    -M "${orderer_home}/msp" \
    --tls.certfiles "${ca_cert}"
  write_node_ou "${orderer_home}/msp"
  if [[ -f "${orderer_home}/msp/signcerts/cert.pem" ]]; then
    mv "${orderer_home}/msp/signcerts/cert.pem" "${orderer_home}/msp/signcerts/orderer.example.com-cert.pem"
  fi

  fabric-ca-client enroll \
    -u "https://orderer:${ORDERER_PASSWORD}@ca-orderer:7054" \
    --caname ca-orderer \
    -M "${orderer_home}/tls" \
    --enrollment.profile tls \
    --csr.hosts orderer.example.com \
    --csr.hosts localhost \
    --csr.hosts saam-medtrace-orderer \
    --tls.certfiles "${ca_cert}"

  copy_one "${orderer_home}/tls/tlscacerts/*" "${orderer_home}/tls/ca.crt"
  copy_one "${orderer_home}/tls/signcerts/*" "${orderer_home}/tls/server.crt"
  copy_one "${orderer_home}/tls/keystore/*" "${orderer_home}/tls/server.key"
  mkdir -p "${orderer_home}/msp/tlscacerts"
  cp "${orderer_home}/tls/ca.crt" "${orderer_home}/msp/tlscacerts/tlsca.example.com-cert.pem"

  fabric-ca-client enroll \
    -u "https://ordererAdmin:${ORDERER_ADMIN_PASSWORD}@ca-orderer:7054" \
    --caname ca-orderer \
    -M "${org_home}/users/Admin@example.com/msp" \
    --tls.certfiles "${ca_cert}"
  write_node_ou "${org_home}/users/Admin@example.com/msp"
}

CA_ORG_BOOTSTRAP="${CA_ORG1_PASSWORD}" enroll_peer_org \
  org1 org1.example.com ca-org1 ca-org1 7054 org1 \
  "${PEER_ORG1_PASSWORD}" "${ORG1_ADMIN_PASSWORD}"

CA_ORG_BOOTSTRAP="${CA_ORG2_PASSWORD}" enroll_peer_org \
  org2 org2.example.com ca-org2 ca-org2 7054 org2 \
  "${PEER_ORG2_PASSWORD}" "${ORG2_ADMIN_PASSWORD}"

enroll_orderer
echo "Enrollment complete"
