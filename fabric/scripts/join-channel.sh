#!/usr/bin/env bash
# Join the orderer and both peers to the medtrace application channel.
set -euo pipefail

cd /work

block=/work/channel-artifacts/medtrace.block
if [[ ! -s "${block}" ]]; then
  echo "Missing genesis block ${block}." >&2
  exit 1
fi

orderer_tls=/work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls

retry() {
  local attempts=$1
  shift
  local try
  for ((try = 1; try <= attempts; try++)); do
    if "$@"; then
      return 0
    fi
    echo "Attempt ${try}/${attempts} failed; retrying." >&2
    sleep 2
  done
  return 1
}

orderer_joined() {
  local listed
  listed=$(osnadmin channel list \
    -o orderer.example.com:7053 \
    --ca-file "${orderer_tls}/ca.crt" \
    --client-cert "${orderer_tls}/server.crt" \
    --client-key "${orderer_tls}/server.key" 2>/dev/null || true)
  [[ "${listed}" == *medtrace* ]]
}

echo "Joining orderer to medtrace"
if orderer_joined; then
  echo "Orderer already has medtrace"
else
  retry 30 osnadmin channel join \
    --channelID medtrace \
    --config-block "${block}" \
    -o orderer.example.com:7053 \
    --ca-file "${orderer_tls}/ca.crt" \
    --client-cert "${orderer_tls}/server.crt" \
    --client-key "${orderer_tls}/server.key"
  orderer_joined
fi

join_peer() {
  local mspid=$1
  local address=$2
  local admin_msp=$3
  local tls_root=$4
  # The tools service points FABRIC_CFG_PATH at configtx.yaml. The peer CLI needs core.yaml.
  export FABRIC_CFG_PATH=/etc/hyperledger/fabric
  export CORE_PEER_LOCALMSPID="${mspid}"
  export CORE_PEER_ADDRESS="${address}"
  export CORE_PEER_MSPCONFIGPATH="${admin_msp}"
  export CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_TLS_ROOTCERT_FILE="${tls_root}"
  echo "Joining ${address} as ${mspid}"
  if ! retry 15 peer channel join -b "${block}"; then
    local listed
    listed=$(peer channel list || true)
    if [[ "${listed}" != *medtrace* ]]; then
      echo "${address} did not join medtrace." >&2
      echo "${listed}" >&2
      exit 1
    fi
  fi
  local listed
  listed=$(peer channel list)
  if [[ "${listed}" != *medtrace* ]]; then
    echo "${address} did not list medtrace after join." >&2
    echo "${listed}" >&2
    exit 1
  fi
}

join_peer \
  Org1MSP \
  peer0.org1.example.com:7051 \
  /work/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp \
  /work/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt

join_peer \
  Org2MSP \
  peer0.org2.example.com:7051 \
  /work/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp \
  /work/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt

echo "Channel join complete"
