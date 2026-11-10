#!/usr/bin/env bash
# Install, approve, and commit the provenance chaincode.
# Package identifiers are the only lines written to stdout.
# Safe to run again on a live network: the packages are byte-identical from one run
# to the next, so the install is a no-op, and a definition that is already committed
# is checked (same package identifier approved by both organizations), not redone.
set -euo pipefail

cd /work
export FABRIC_CFG_PATH=/etc/hyperledger/fabric
export CORE_PEER_TLS_ENABLED=true

ORDERER=orderer.example.com:7050
ORDERER_CA=/work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/ca.crt
CHANNEL=medtrace
CC_NAME=provenance
POLICY="AND('Org1MSP.peer','Org2MSP.peer')"
ORG1=/work/organizations/peerOrganizations/org1.example.com
ORG2=/work/organizations/peerOrganizations/org2.example.com

use_peer() {
  local mspid=$1
  local address=$2
  local admin_msp=$3
  local tls_root=$4
  export CORE_PEER_LOCALMSPID="${mspid}"
  export CORE_PEER_ADDRESS="${address}"
  export CORE_PEER_MSPCONFIGPATH="${admin_msp}"
  export CORE_PEER_TLS_ROOTCERT_FILE="${tls_root}"
}

use_org1() {
  use_peer Org1MSP peer0.org1.example.com:7051 \
    "${ORG1}/users/Admin@org1.example.com/msp" \
    "${ORG1}/peers/peer0.org1.example.com/tls/ca.crt"
}

use_org2() {
  use_peer Org2MSP peer0.org2.example.com:7051 \
    "${ORG2}/users/Admin@org2.example.com/msp" \
    "${ORG2}/peers/peer0.org2.example.com/tls/ca.crt"
}

# Print the last lines of a peer command's output, then stop. The peer's messages
# carry no credentials; they are what tells the operator why a step failed.
fail_with_log() {
  local message=$1
  local log=$2
  echo "${message}" >&2
  tail -n 8 "${log}" >&2 || true
  exit 1
}

package_id() {
  peer lifecycle chaincode calculatepackageid "$1"
}

install_package() {
  local package=$1
  local label=$2
  if peer lifecycle chaincode install "${package}" >/tmp/cc-install.txt 2>&1; then
    return 0
  fi
  if grep -q "already successfully installed" /tmp/cc-install.txt; then
    return 0
  fi
  fail_with_log "Chaincode install failed for ${label}." /tmp/cc-install.txt
}

approve() {
  local package=$1
  peer lifecycle chaincode approveformyorg \
    -o "${ORDERER}" \
    --channelID "${CHANNEL}" \
    --name "${CC_NAME}" \
    --version 1 \
    --sequence 1 \
    --package-id "${package}" \
    --signature-policy "${POLICY}" \
    --tls --cafile "${ORDERER_CA}" >/tmp/cc-approve.txt 2>&1 \
    || fail_with_log "Chaincode approval failed." /tmp/cc-approve.txt
}

committed() {
  peer lifecycle chaincode querycommitted --channelID "${CHANNEL}" --name "${CC_NAME}" >/dev/null 2>&1
}

# The package identifier the current organization approved, empty if none.
approved_package_id() {
  peer lifecycle chaincode queryapproved --channelID "${CHANNEL}" --name "${CC_NAME}" 2>/dev/null \
    | sed -n 's/.*package-id: \([^,]*\).*/\1/p' || true
}

require_approved() {
  local expected=$1
  local actual
  actual=$(approved_package_id)
  if [[ "${actual}" != "${expected}" ]]; then
    echo "${CC_NAME} is already committed with a different package for ${CORE_PEER_LOCALMSPID}." >&2
    echo "This network does not upgrade a definition: run fabric/network.sh stop, then start." >&2
    exit 1
  fi
}

use_org1
install_package /work/runtime/cc/org1.tgz "${CC_NAME}"
org1_id=$(package_id /work/runtime/cc/org1.tgz)

use_org2
install_package /work/runtime/cc/org2.tgz "${CC_NAME}"
org2_id=$(package_id /work/runtime/cc/org2.tgz)

if [[ -z "${org1_id}" || -z "${org2_id}" ]]; then
  echo "Could not compute the chaincode package identifiers." >&2
  exit 1
fi

if committed; then
  echo "${CC_NAME} is already committed on ${CHANNEL}; checking the approved packages." >&2
  require_approved "${org2_id}"
  use_org1
  require_approved "${org1_id}"
else
  use_org1
  approve "${org1_id}"
  use_org2
  approve "${org2_id}"
  peer lifecycle chaincode commit \
    -o "${ORDERER}" \
    --channelID "${CHANNEL}" \
    --name "${CC_NAME}" \
    --version 1 \
    --sequence 1 \
    --signature-policy "${POLICY}" \
    --tls --cafile "${ORDERER_CA}" \
    --peerAddresses peer0.org1.example.com:7051 \
    --tlsRootCertFiles "${ORG1}/peers/peer0.org1.example.com/tls/ca.crt" \
    --peerAddresses peer0.org2.example.com:7051 \
    --tlsRootCertFiles "${ORG2}/peers/peer0.org2.example.com/tls/ca.crt" \
    >/tmp/cc-commit.txt 2>&1 \
    || fail_with_log "Chaincode commit failed." /tmp/cc-commit.txt
fi

# Whatever happened above, the definition must now be on the ledger.
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if committed; then
    break
  fi
  if [[ "${attempt}" -eq 10 ]]; then
    echo "${CC_NAME} is not committed on ${CHANNEL}." >&2
    exit 1
  fi
  sleep 1
done

printf 'PACKAGE_ORG1=%s\n' "${org1_id}"
printf 'PACKAGE_ORG2=%s\n' "${org2_id}"
