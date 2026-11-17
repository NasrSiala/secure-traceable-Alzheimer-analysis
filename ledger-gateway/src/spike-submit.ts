import * as path from "node:path";

import { buildApp } from "./app";
import { connectLedger } from "./fabric-client";
import { probeArtifact } from "./probe-artifact";
import { envSetting } from "./settings";
import { tokensForWallet } from "./tokens";

const identityName = envSetting("SPIKE_IDENTITY", "agent-ingestion");
const operation = envSetting("SPIKE_OP", "write");
const key = envSetting("SPIKE_KEY", "attribute-probe");

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
  const walletDir = envSetting("WALLET_DIR", path.resolve(__dirname, "../../fabric/wallet"));
  const tokens = await tokensForWallet(walletDir);
  const token = tokens.tokenFor(identityName);
  const ledger = await connectLedger();
  const app = buildApp({ tokens, ledger });
  try {
    const base = await app.listen({ host: "127.0.0.1", port: 0 });
    const probe = probeArtifact(key);
    const response =
      operation === "write"
        ? await fetch(`${base}/ledger/artifacts`, {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "X-Agent-Token": token,
            },
            body: probe.payload,
          })
        : await fetch(`${base}/ledger/artifacts/${probe.artifactId}`, {
            headers: { "X-Agent-Token": token },
          });
    const text = await response.text();
    if (!response.ok) {
      process.stderr.write(`${text}\n`);
      process.exitCode = 1;
      return;
    }
    process.stdout.write(`${text}\n`);
  } finally {
    await app.close();
    ledger.close();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "spike failed";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
