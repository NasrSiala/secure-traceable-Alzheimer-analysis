import { randomBytes } from "node:crypto";
import * as path from "node:path";

import { buildApp } from "./app";
import { isErrorEnvelope, type FailureReport } from "./errors";
import { connectLedger } from "./fabric-client";
import { probeArtifact } from "./probe-artifact";
import { envSetting } from "./settings";
import { tokensForWallet } from "./tokens";

const MISSING_ID = "00000000-0000-4000-8000-000000000099";

function report(payload: Record<string, unknown>, ok: boolean): void {
  process.stdout.write(`GATEWAY_CHECK ${JSON.stringify(payload)}\n`);
  if (!ok) {
    process.exitCode = 1;
  }
}

function logFailure(failure: FailureReport): void {
  process.stderr.write(`${JSON.stringify({ event: "ledger-failure", ...failure })}\n`);
}

function codeOf(value: unknown): string {
  return isErrorEnvelope(value) ? value.error.code : "";
}

async function main(): Promise<void> {
  const scenario = envSetting("GATEWAY_SCENARIO", "flow");
  if (scenario !== "flow" && scenario !== "down") {
    throw new Error("GATEWAY_SCENARIO must be flow or down");
  }
  const walletDir = envSetting("WALLET_DIR", path.resolve(__dirname, "../../fabric/wallet"));
  const tokens = await tokensForWallet(walletDir);
  const token = tokens.tokenFor("agent-ingestion");
  const ledger = await connectLedger();
  const app = buildApp({ tokens, ledger, onFailure: logFailure });
  try {
    const base = await app.listen({ host: "127.0.0.1", port: 0 });
    // A run of its own: CreateArtifactRecord refuses an existing artifactId (AC-07.3), so a fixed
    // identifier would make the second run on one network fail with 409.
    const key = `gateway-${randomBytes(6).toString("hex")}`;
    const probe = probeArtifact(key);
    const forgedProbe = probeArtifact(`${key}-forged`);
    if (scenario === "down") {
      const response = await fetch(`${base}/ledger/artifacts/${probe.artifactId}`, {
        headers: { "X-Agent-Token": token },
      });
      const body: unknown = await response.json();
      const code = codeOf(body);
      report(
        {
          scenario,
          status: response.status,
          code,
          shape: code !== "",
        },
        response.status === 502 && code === "UNAVAILABLE",
      );
      return;
    }

    const created = await fetch(`${base}/ledger/artifacts`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Agent-Token": token,
      },
      body: probe.payload,
    });
    const createdBody = (await created.json()) as { artifactId?: string; sha256?: string };
    const read = await fetch(`${base}/ledger/artifacts/${probe.artifactId}`, {
      headers: { "X-Agent-Token": token },
    });
    const readBody = (await read.json()) as {
      artifactId?: string;
      sha256?: string;
      creatorMspId?: string;
      creatorId?: string;
      creatorAgent?: string;
    };
    const duplicate = await fetch(`${base}/ledger/artifacts`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Agent-Token": token,
      },
      body: probe.payload,
    });
    const duplicateBody: unknown = await duplicate.json();
    const missing = await fetch(`${base}/ledger/artifacts/${MISSING_ID}`, {
      headers: { "X-Agent-Token": token },
    });
    const missingBody: unknown = await missing.json();
    const unauthorized = await fetch(`${base}/ledger/artifacts/${probe.artifactId}`, {
      headers: { "X-Agent-Token": "not-a-real-token" },
    });
    const unauthorizedBody: unknown = await unauthorized.json();
    // NFR-06: who created a record comes from the certificate. A client that names its own
    // creator is refused, and nothing is stored under the identifier it sent.
    const forgedBody = JSON.stringify({
      ...(JSON.parse(forgedProbe.payload) as Record<string, unknown>),
      creatorMspId: "Org9MSP",
      creatorId: "x509::/CN=someone-else",
      creatorAgent: "validation",
    });
    const forged = await fetch(`${base}/ledger/artifacts`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Agent-Token": token,
      },
      body: forgedBody,
    });
    const forgedReply: unknown = await forged.json();
    const forgedRead = await fetch(`${base}/ledger/artifacts/${forgedProbe.artifactId}`, {
      headers: { "X-Agent-Token": token },
    });
    const forgedCode = codeOf(forgedReply);
    const duplicateCode = codeOf(duplicateBody);
    const missingCode = codeOf(missingBody);
    const unauthorizedCode = codeOf(unauthorizedBody);
    const ok =
      created.status === 200 &&
      createdBody.artifactId === probe.artifactId &&
      read.status === 200 &&
      readBody.artifactId === probe.artifactId &&
      readBody.sha256 === createdBody.sha256 &&
      readBody.creatorMspId === "Org1MSP" &&
      readBody.creatorAgent === "ingestion" &&
      readBody.creatorId?.includes("CN=agent-ingestion") === true &&
      forged.status === 400 &&
      forgedCode === "SCHEMA" &&
      forgedRead.status === 404 &&
      duplicate.status === 409 &&
      duplicateCode === "DUPLICATE" &&
      missing.status === 404 &&
      missingCode === "NOT_FOUND" &&
      unauthorized.status === 401 &&
      unauthorizedCode === "UNAUTHORIZED" &&
      !JSON.stringify(unauthorizedBody).includes("not-a-real-token");
    report(
      {
        scenario,
        create: created.status,
        read: read.status,
        creatorMspId: readBody.creatorMspId ?? "",
        creatorId: readBody.creatorId ?? "",
        creatorAgent: readBody.creatorAgent ?? "",
        forged: forged.status,
        forgedCode,
        forgedStored: forgedRead.status !== 404,
        duplicate: duplicate.status,
        duplicateCode,
        missing: missing.status,
        missingCode,
        unauthorized: unauthorized.status,
        unauthorizedCode,
        shape: duplicateCode !== "" && missingCode !== "" && unauthorizedCode !== "",
      },
      ok,
    );
  } finally {
    await app.close();
    ledger.close();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "gateway check failed";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
