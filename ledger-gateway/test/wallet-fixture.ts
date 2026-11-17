import { generateKeyPairSync } from "node:crypto";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

import type { LedgerSettings } from "../src/fabric-client";

// A wallet on disk that holds what `connectLedger` reads and nothing a peer would accept:
// the certificate is only handed to the Gateway client, which sends it to the peer, and
// nothing in these tests parses it or answers it.

export async function enroll(
  wallet: string,
  identity: string,
  mspId = "Org1MSP",
): Promise<void> {
  const home = path.join(wallet, identity);
  await mkdir(home, { recursive: true });
  const { privateKey } = generateKeyPairSync("ec", { namedCurve: "P-256" });
  await writeFile(path.join(home, "cert.pem"), "certificate");
  await writeFile(path.join(home, "key.pem"), privateKey.export({ type: "pkcs8", format: "pem" }));
  await writeFile(path.join(home, "msp-id"), `${mspId}\n`);
}

export async function walletSettings(): Promise<LedgerSettings> {
  const walletDir = await mkdtemp(path.join(tmpdir(), "saam-client-"));
  await enroll(walletDir, "agent-ingestion");
  const peerTlsCert = path.join(walletDir, "peer0-org1-tls-ca.crt");
  await writeFile(peerTlsCert, "authority");
  return {
    walletDir,
    // Nothing listens on port 1: a call that reaches the network fails at once with UNAVAILABLE.
    peerEndpoint: "127.0.0.1:1",
    peerTlsCert,
    channelName: "medtrace",
    chaincodeName: "provenance",
  };
}
