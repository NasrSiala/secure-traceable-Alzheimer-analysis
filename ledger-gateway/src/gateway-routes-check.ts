import { randomBytes } from "node:crypto";
import * as path from "node:path";

import { buildApp } from "./app";
import { type FailureReport, isErrorEnvelope } from "./errors";
import { connectLedger } from "./fabric-client";
import { artifactIdForProbe } from "./probe-artifact";
import { envSetting } from "./settings";
import { tokensForWallet } from "./tokens";

// T2.6 (2/2) on the test network, through the HTTP routes and the real certificates: the history
// of a case of seven artifacts, and the model registry with and without role=model-admin. With
// the artifact routes it makes the five routes of TRD 8.2.

const PIPELINE = [
  "original",
  "processed",
  "features",
  "prediction",
  "validation",
  "explanation",
  "final_result",
] as const;

const SHA256 = "ab".repeat(32);
const VERSION = "1.0.0";
const UNKNOWN_TOKEN = "not-a-real-token";

// A run of its own: the ledger keeps every artifact of a case and refuses an existing artifactId
// or model name and version, so fixed identifiers would make the second run on one network fail,
// or find 14 records where it expects 7.
const RUN = randomBytes(8).toString("hex");
const CASE_ID = `CASE-${artifactIdForProbe(`routes-${RUN}-case`)}`;
const EMPTY_CASE_ID = `CASE-${artifactIdForProbe(`routes-${RUN}-empty`)}`;
const NAME = `route-${RUN}`;

interface Reply {
  status: number;
  body: unknown;
}

interface StoredArtifact {
  artifactId?: string;
  artifactType?: string;
  parentArtifactId?: string | null;
  creatorAgent?: string;
}

function report(fields: Record<string, unknown>, ok: boolean): void {
  process.stdout.write(`ROUTES_CHECK ${JSON.stringify(fields)}\n`);
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

function artifactBody(
  rank: number,
  artifactId: string,
  parent: string | null,
): Record<string, unknown> {
  return {
    artifactId,
    caseId: CASE_ID,
    artifactType: PIPELINE[rank],
    sha256: SHA256,
    createdAt: "2026-11-09T12:00:00.000Z",
    softwareVersion: "0.1.0",
    modelVersion: null,
    parentArtifactId: parent,
    offchainRef: `artifact://${artifactId}`,
  };
}

function modelBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { name: NAME, version: VERSION, sha256: SHA256, framework: "pytorch", ...overrides };
}

async function main(): Promise<void> {
  const walletDir = envSetting("WALLET_DIR", path.resolve(__dirname, "../../fabric/wallet"));
  const tokens = await tokensForWallet(walletDir);
  const agentToken = tokens.tokenFor("agent-ingestion");
  const adminToken = tokens.tokenFor("model-admin");
  const verifierToken = tokens.tokenFor("verifier");
  const ledger = await connectLedger();
  const app = buildApp({ tokens, ledger, onFailure: logFailure });
  try {
    const base = await app.listen({ host: "127.0.0.1", port: 0 });
    const send = async (
      method: "GET" | "POST",
      url: string,
      token: string,
      payload?: Record<string, unknown>,
    ): Promise<Reply> => {
      const headers: Record<string, string> = { "X-Agent-Token": token };
      if (payload !== undefined) {
        headers["content-type"] = "application/json";
      }
      const response = await fetch(`${base}${url}`, {
        method,
        headers,
        body: payload === undefined ? undefined : JSON.stringify(payload),
      });
      return { status: response.status, body: (await response.json()) as unknown };
    };

    // POST /ledger/artifacts: the seven artifacts of one case, each the child of the previous one.
    const ids = PIPELINE.map((_type, rank) => artifactIdForProbe(`routes-${RUN}-${String(rank)}`));
    let created = 0;
    for (let rank = 0; rank < PIPELINE.length; rank += 1) {
      const parent = rank === 0 ? null : (ids[rank - 1] ?? null);
      const reply = await send(
        "POST",
        "/ledger/artifacts",
        agentToken,
        artifactBody(rank, ids[rank] ?? "", parent),
      );
      if (reply.status === 200) {
        created += 1;
      }
    }
    // GET /ledger/artifacts/{id}
    const lastId = ids[PIPELINE.length - 1] ?? "";
    const artifactRead = await send("GET", `/ledger/artifacts/${lastId}`, agentToken);

    // GET /ledger/cases/{caseId}: seven records, parent to child; an unknown case is empty.
    const history = await send("GET", `/ledger/cases/${CASE_ID}`, agentToken);
    const records = Array.isArray(history.body) ? (history.body as StoredArtifact[]) : [];
    const types = records.map((record) => record.artifactType ?? "");
    const parentsOk = records.every((record, rank) =>
      rank === 0 ? record.parentArtifactId === null : record.parentArtifactId === ids[rank - 1],
    );
    const verifierHistory = await send("GET", `/ledger/cases/${CASE_ID}`, verifierToken);
    const emptyHistory = await send("GET", `/ledger/cases/${EMPTY_CASE_ID}`, agentToken);
    const badCase = await send("GET", "/ledger/cases/CASE-1", agentToken);

    // POST /ledger/models without role=model-admin: 403 FORBIDDEN, and nothing is stored.
    const agentRegistration = await send("POST", "/ledger/models", agentToken, modelBody());
    const verifierRegistration = await send("POST", "/ledger/models", verifierToken, modelBody());
    const afterRefusal = await send("GET", `/ledger/models/${NAME}/${VERSION}`, adminToken);

    // POST /ledger/models with role=model-admin, then GET /ledger/models/{name}/{version}.
    const registration = await send("POST", "/ledger/models", adminToken, modelBody());
    const stored = registration.body as Record<string, unknown>;
    const read = await send("GET", `/ledger/models/${NAME}/${VERSION}`, adminToken);
    const readByVerifier = await send("GET", `/ledger/models/${NAME}/${VERSION}`, verifierToken);
    const readByAgent = await send("GET", `/ledger/models/${NAME}/${VERSION}`, agentToken);
    const sameRecord = (reply: Reply): boolean => JSON.stringify(reply.body) === JSON.stringify(stored);

    const duplicate = await send(
      "POST",
      "/ledger/models",
      adminToken,
      modelBody({ sha256: "cd".repeat(32) }),
    );
    const afterDuplicate = await send("GET", `/ledger/models/${NAME}/${VERSION}`, adminToken);
    const missing = await send("GET", `/ledger/models/${NAME}/9.9.9`, adminToken);
    const extraField = await send(
      "POST",
      "/ledger/models",
      adminToken,
      modelBody({ version: "3.0.0", patientName: "hidden" }),
    );
    const afterExtra = await send("GET", `/ledger/models/${NAME}/3.0.0`, adminToken);
    const unauthorized = await send("GET", `/ledger/models/${NAME}/${VERSION}`, UNKNOWN_TOKEN);

    const refusals = [
      agentRegistration,
      verifierRegistration,
      duplicate,
      missing,
      extraField,
      unauthorized,
      badCase,
    ];
    const shape = refusals.every((reply) => isErrorEnvelope(reply.body));
    // The refusals answer requests made with every token below (agent, verifier and administrator
    // are real): none of them may come back in a reply (AUD-101).
    const refusalText = JSON.stringify(refusals.map((reply) => reply.body));
    const leaked = [agentToken, adminToken, verifierToken, UNKNOWN_TOKEN].some((token) =>
      refusalText.includes(token),
    );

    const ok =
      created === PIPELINE.length &&
      artifactRead.status === 200 &&
      history.status === 200 &&
      records.length === PIPELINE.length &&
      types.join(",") === PIPELINE.join(",") &&
      parentsOk &&
      records.every((record) => record.creatorAgent === "ingestion") &&
      verifierHistory.status === 200 &&
      JSON.stringify(verifierHistory.body) === JSON.stringify(history.body) &&
      emptyHistory.status === 200 &&
      JSON.stringify(emptyHistory.body) === "[]" &&
      badCase.status === 400 &&
      codeOf(badCase.body) === "SCHEMA" &&
      agentRegistration.status === 403 &&
      codeOf(agentRegistration.body) === "FORBIDDEN" &&
      verifierRegistration.status === 403 &&
      codeOf(verifierRegistration.body) === "FORBIDDEN" &&
      afterRefusal.status === 404 &&
      registration.status === 200 &&
      stored.docType === "model" &&
      stored.name === NAME &&
      String(stored.registeredBy).includes("CN=model-admin") &&
      read.status === 200 &&
      sameRecord(read) &&
      sameRecord(readByVerifier) &&
      sameRecord(readByAgent) &&
      duplicate.status === 409 &&
      codeOf(duplicate.body) === "DUPLICATE" &&
      sameRecord(afterDuplicate) &&
      missing.status === 404 &&
      codeOf(missing.body) === "NOT_FOUND" &&
      extraField.status === 400 &&
      codeOf(extraField.body) === "SCHEMA" &&
      afterExtra.status === 404 &&
      unauthorized.status === 401 &&
      codeOf(unauthorized.body) === "UNAUTHORIZED" &&
      shape &&
      !leaked;
    report(
      {
        created,
        artifactRead: artifactRead.status,
        history: history.status,
        count: records.length,
        types,
        parentsOk,
        verifierHistory: verifierHistory.status,
        emptyCaseCount: Array.isArray(emptyHistory.body) ? emptyHistory.body.length : -1,
        badCase: badCase.status,
        badCaseCode: codeOf(badCase.body),
        agentRegistration: agentRegistration.status,
        agentRegistrationCode: codeOf(agentRegistration.body),
        verifierRegistration: verifierRegistration.status,
        verifierRegistrationCode: codeOf(verifierRegistration.body),
        refusedStored: afterRefusal.status !== 404,
        registration: registration.status,
        docType: String(stored.docType ?? ""),
        registeredBy: String(stored.registeredBy ?? ""),
        read: read.status,
        readBack: sameRecord(read),
        readByVerifier: sameRecord(readByVerifier),
        readByAgent: sameRecord(readByAgent),
        duplicate: duplicate.status,
        duplicateCode: codeOf(duplicate.body),
        duplicateChangedRecord: !sameRecord(afterDuplicate),
        missing: missing.status,
        missingCode: codeOf(missing.body),
        extraField: extraField.status,
        extraFieldCode: codeOf(extraField.body),
        extraFieldStored: afterExtra.status !== 404,
        unauthorized: unauthorized.status,
        unauthorizedCode: codeOf(unauthorized.body),
        shape,
        tokenLeaked: leaked,
      },
      ok,
    );
  } finally {
    await app.close();
    ledger.close();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "gateway routes check failed";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
