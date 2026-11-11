import * as crypto from "node:crypto";
import { promises as fs } from "node:fs";
import * as path from "node:path";

import * as grpc from "@grpc/grpc-js";
import { connect, hash, signers } from "@hyperledger/fabric-gateway";

const identityName = process.env.SPIKE_IDENTITY ?? "agent-ingestion";
const operation = process.env.SPIKE_OP ?? "write";
const key = process.env.SPIKE_KEY ?? "attribute-probe";
// Defaults are for a host with Node: the Org1 peer is published on 127.0.0.1:18051,
// and the name to dial is "localhost" because the IP address is not one of the names
// in the peer's TLS certificate (peer0.org1.example.com, localhost, saam-medtrace-peer0-org1).
// The identities and the peer's TLS CA certificate both live in the wallet
// (fabric/enroll-identities.sh): organizations/ is readable by root only on Linux.
// Compose overrides these for the container run (fabric/spike-submit.sh).
const walletDir = process.env.WALLET_DIR ?? path.resolve(__dirname, "../../fabric/wallet");
const peerEndpoint = process.env.PEER_ENDPOINT ?? "localhost:18051";
const peerTlsCert = process.env.PEER_TLS_CERT ?? path.join(walletDir, "peer0-org1-tls-ca.crt");
const channelName = process.env.CHANNEL_NAME ?? "medtrace";
const chaincodeName = process.env.CHAINCODE_NAME ?? "identity-spike";

function requireSlug(value: string, label: string): void {
  if (!/^[a-z0-9-]+$/.test(value)) {
    throw new Error(`${label} contains unsupported characters`);
  }
}

async function main(): Promise<void> {
  requireSlug(identityName, "SPIKE_IDENTITY");
  requireSlug(key, "SPIKE_KEY");
  if (operation !== "write" && operation !== "read") {
    throw new Error("SPIKE_OP must be write or read");
  }
  if (peerTlsCert === "") {
    throw new Error("PEER_TLS_CERT is required");
  }

  const home = path.join(walletDir, identityName);
  const certificate = await fs.readFile(path.join(home, "cert.pem"));
  const privateKeyPem = await fs.readFile(path.join(home, "key.pem"));
  const mspId = (await fs.readFile(path.join(home, "msp-id"), "utf8")).trim();
  const tlsRoot = await fs.readFile(peerTlsCert);
  const signer = signers.newPrivateKeySigner(crypto.createPrivateKey(privateKeyPem));
  const client = new grpc.Client(peerEndpoint, grpc.credentials.createSsl(tlsRoot));
  const gateway = connect({
    client,
    identity: { mspId, credentials: certificate },
    signer,
    hash: hash.sha256,
  });

  try {
    const contract = gateway.getNetwork(channelName).getContract(chaincodeName, "IdentitySpike");
    const result =
      operation === "write"
        ? await contract.submitTransaction("Write", key)
        : await contract.evaluateTransaction("Read", key);
    process.stdout.write(Buffer.from(result).toString("utf8"));
    process.stdout.write("\n");
  } finally {
    gateway.close();
    client.close();
  }
}

function describe(error: unknown): string {
  if (!(error instanceof Error)) {
    return String(error);
  }
  const details = (error as { details?: { mspId?: string; message?: string }[] }).details;
  if (!Array.isArray(details) || details.length === 0) {
    return error.message;
  }
  const lines = details.map((item) => `${item.mspId ?? "peer"}: ${item.message ?? ""}`);
  return `${error.message}\n${lines.join("\n")}`;
}

main().catch((error: unknown) => {
  process.stderr.write(`${describe(error)}\n`);
  process.exitCode = 1;
});
