import { randomBytes } from "node:crypto";

import { chaincodeFailure } from "./errors";
import { connectLedger, type LedgerSession } from "./fabric-client";
import { artifactIdForProbe } from "./probe-artifact";

const PIPELINE = [
  "original",
  "processed",
  "features",
  "prediction",
  "validation",
  "explanation",
  "final_result",
] as const;

// A run of its own: CreateArtifactRecord refuses an existing artifactId (AC-07.3) and a case
// keeps every artifact written under it, so fixed identifiers would make the second run on one
// network fail, or find 14 records where it expects 7.
const RUN = randomBytes(10).toString("hex");
const CASE_ID = `CASE-${artifactIdForProbe(`history-${RUN}-case`)}`;
const OTHER_CASE_ID = `CASE-${artifactIdForProbe(`history-${RUN}-other-case`)}`;
const EMPTY_CASE_ID = `CASE-${artifactIdForProbe(`history-${RUN}-empty-case`)}`;

// The first artifact of the chain has the largest identifier and the last one the smallest, so
// a history sorted by key would come out reversed: the order must come from the parent links.
function chainId(rank: number): string {
  const digit = String(PIPELINE.length - rank);
  const hex = RUN;
  return (
    `${digit}${hex.slice(0, 7)}-${hex.slice(7, 11)}-4${hex.slice(11, 14)}-8${hex.slice(14, 17)}-` +
    `${hex.slice(17, 20)}${"0".repeat(8)}${digit}`
  );
}

function payload(
  artifactId: string,
  caseId: string,
  artifactType: string,
  parent: string | null,
  extra: Record<string, string> = {},
): string {
  return JSON.stringify({
    artifactId,
    caseId,
    artifactType,
    sha256: "ab".repeat(32),
    createdAt: "2026-11-09T12:00:00.000Z",
    softwareVersion: "0.1.0",
    modelVersion: null,
    parentArtifactId: parent,
    offchainRef: `artifact://${artifactId}`,
    ...extra,
  });
}

interface StoredArtifact {
  artifactId?: string;
  artifactType?: string;
  parentArtifactId?: string | null;
  txTimestamp?: string;
  creatorMspId?: string;
  creatorId?: string;
  creatorAgent?: string;
}

function report(body: Record<string, unknown>, ok: boolean): void {
  process.stdout.write(`HISTORY_CHECK ${JSON.stringify(body)}\n`);
  if (!ok) {
    process.exitCode = 1;
  }
}

async function refusalCode(attempt: Promise<unknown>): Promise<string> {
  try {
    await attempt;
    return "";
  } catch (error) {
    return chaincodeFailure(error).body.error.code;
  }
}

async function history(ledger: LedgerSession, caseId: string): Promise<StoredArtifact[]> {
  const parsed: unknown = JSON.parse(await ledger.history("agent-ingestion", caseId));
  return Array.isArray(parsed) ? (parsed as StoredArtifact[]) : [];
}

async function main(): Promise<void> {
  const ledger = await connectLedger();
  try {
    for (let rank = 0; rank < PIPELINE.length; rank += 1) {
      const parent = rank === 0 ? null : chainId(rank - 1);
      const type = PIPELINE[rank] ?? "original";
      await ledger.create("agent-ingestion", payload(chainId(rank), CASE_ID, type, parent));
    }
    const otherId = artifactIdForProbe(`history-${RUN}-other`);
    await ledger.create("agent-ingestion", payload(otherId, OTHER_CASE_ID, "original", null));

    // NFR-06: a client that names its own creator is refused by the chaincode, and nothing is
    // stored under the identifier it sent.
    const forgedId = artifactIdForProbe(`history-${RUN}-forged`);
    const forgedCode = await refusalCode(
      ledger.create(
        "agent-ingestion",
        payload(forgedId, EMPTY_CASE_ID, "original", null, {
          creatorMspId: "Org9MSP",
          creatorId: "x509::/CN=someone-else",
          creatorAgent: "validation",
        }),
      ),
    );
    const forgedReadCode = await refusalCode(ledger.read("agent-ingestion", forgedId));

    const records = await history(ledger, CASE_ID);
    const otherRecords = await history(ledger, OTHER_CASE_ID);
    const emptyRecords = await history(ledger, EMPTY_CASE_ID);
    const types = records.map((record) => record.artifactType ?? "");
    const parentsOk = records.every((record, rank) =>
      rank === 0 ? record.parentArtifactId === null : record.parentArtifactId === chainId(rank - 1),
    );
    const creatorsOk = records.every(
      (record) =>
        record.creatorMspId === "Org1MSP" &&
        record.creatorAgent === "ingestion" &&
        record.creatorId?.includes("CN=agent-ingestion") === true &&
        typeof record.txTimestamp === "string" &&
        record.txTimestamp !== "",
    );
    const ok =
      records.length === PIPELINE.length &&
      types.join(",") === PIPELINE.join(",") &&
      parentsOk &&
      creatorsOk &&
      otherRecords.length === 1 &&
      otherRecords[0]?.artifactId === otherId &&
      emptyRecords.length === 0 &&
      forgedCode === "SCHEMA" &&
      forgedReadCode === "NOT_FOUND";
    report(
      {
        count: records.length,
        types,
        otherCaseCount: otherRecords.length,
        emptyCaseCount: emptyRecords.length,
        forgedCode,
        forgedStored: forgedReadCode !== "NOT_FOUND",
        creatorMspId: records[0]?.creatorMspId ?? "",
        creatorId: records[0]?.creatorId ?? "",
        creatorAgent: records[0]?.creatorAgent ?? "",
      },
      ok,
    );
  } finally {
    ledger.close();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "history check failed";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
