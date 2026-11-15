import { randomBytes } from "node:crypto";

import { chaincodeFailure } from "./errors";
import { connectLedger, type LedgerSession } from "./fabric-client";

// A run of its own: RegisterModel refuses an existing name and version, and the ledger keeps
// every model, so a fixed name would make the second run on one network fail.
const RUN = randomBytes(8).toString("hex");
const NAME = `check-${RUN}`;
const VERSION = "1.0.0";
const SHA256 = "ab".repeat(32);

const ADMIN = "model-admin";
const VERIFIER = "verifier";
const AGENT = "agent-ingestion";

interface StoredModel {
  docType?: string;
  name?: string;
  version?: string;
  sha256?: string;
  framework?: string;
  registeredAt?: string;
  registeredBy?: string;
}

function body(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    name: NAME,
    version: VERSION,
    sha256: SHA256,
    framework: "pytorch",
    ...overrides,
  });
}

function report(fields: Record<string, unknown>, ok: boolean): void {
  process.stdout.write(`MODEL_CHECK ${JSON.stringify(fields)}\n`);
  if (!ok) {
    process.exitCode = 1;
  }
}

// "" when the call succeeded, otherwise the code the chaincode refused with.
async function refusalCode(attempt: Promise<unknown>): Promise<string> {
  try {
    await attempt;
    return "";
  } catch (error) {
    return chaincodeFailure(error).body.error.code;
  }
}

async function storedModel(
  ledger: LedgerSession,
  identity: string,
  name: string,
  version: string,
): Promise<StoredModel> {
  return JSON.parse(await ledger.getModel(identity, name, version)) as StoredModel;
}

async function main(): Promise<void> {
  const ledger = await connectLedger();
  try {
    // AC-04.3: the identity with role=model-admin registers; the record comes back as stored.
    const registered = JSON.parse(await ledger.registerModel(ADMIN, body())) as StoredModel;
    const read = await storedModel(ledger, ADMIN, NAME, VERSION);
    // Reading needs no attribute: the verifier of Org2 reads the same record.
    const readByVerifier = await storedModel(ledger, VERIFIER, NAME, VERSION);
    const readByAgent = await storedModel(ledger, AGENT, NAME, VERSION);

    // A second registration of the same name and version is a duplicate and changes nothing.
    const duplicateCode = await refusalCode(
      ledger.registerModel(ADMIN, body({ sha256: "cd".repeat(32), framework: "onnx" })),
    );
    const afterDuplicate = await storedModel(ledger, ADMIN, NAME, VERSION);

    // Only role=model-admin registers: the verifier has no attribute, the agent has another.
    const otherVersion = "2.0.0";
    const verifierCode = await refusalCode(
      ledger.registerModel(VERIFIER, body({ version: otherVersion })),
    );
    const agentCode = await refusalCode(
      ledger.registerModel(AGENT, body({ version: otherVersion })),
    );
    const refusedStoredCode = await refusalCode(
      ledger.getModel(ADMIN, NAME, otherVersion),
    );

    // Closed schema: a field outside Schema 5.2 is refused, and nothing is stored under it.
    const extraVersion = "3.0.0";
    const extraFieldCode = await refusalCode(
      ledger.registerModel(ADMIN, body({ version: extraVersion, patientName: "hidden" })),
    );
    const extraStoredCode = await refusalCode(ledger.getModel(ADMIN, NAME, extraVersion));

    // A model that was never registered is a typed NOT_FOUND, and a malformed lookup a SCHEMA.
    const absentCode = await refusalCode(ledger.getModel(ADMIN, NAME, "9.9.9"));
    const malformedCode = await refusalCode(ledger.getModel(ADMIN, NAME, "latest"));

    const ok =
      registered.docType === "model" &&
      registered.name === NAME &&
      registered.version === VERSION &&
      registered.sha256 === SHA256 &&
      registered.registeredBy?.includes("CN=model-admin") === true &&
      typeof registered.registeredAt === "string" &&
      registered.registeredAt !== "" &&
      JSON.stringify(read) === JSON.stringify(registered) &&
      JSON.stringify(readByVerifier) === JSON.stringify(registered) &&
      JSON.stringify(readByAgent) === JSON.stringify(registered) &&
      duplicateCode === "DUPLICATE" &&
      JSON.stringify(afterDuplicate) === JSON.stringify(registered) &&
      verifierCode === "FORBIDDEN" &&
      agentCode === "FORBIDDEN" &&
      refusedStoredCode === "NOT_FOUND" &&
      extraFieldCode === "SCHEMA" &&
      extraStoredCode === "NOT_FOUND" &&
      absentCode === "NOT_FOUND" &&
      malformedCode === "SCHEMA";
    report(
      {
        registeredBy: registered.registeredBy ?? "",
        registeredAt: registered.registeredAt ?? "",
        docType: registered.docType ?? "",
        readBack: JSON.stringify(read) === JSON.stringify(registered),
        readByVerifier: JSON.stringify(readByVerifier) === JSON.stringify(registered),
        readByAgent: JSON.stringify(readByAgent) === JSON.stringify(registered),
        duplicateCode,
        duplicateChangedRecord: JSON.stringify(afterDuplicate) !== JSON.stringify(registered),
        verifierCode,
        agentCode,
        refusedStored: refusedStoredCode !== "NOT_FOUND",
        extraFieldCode,
        extraFieldStored: extraStoredCode !== "NOT_FOUND",
        absentCode,
        malformedCode,
      },
      ok,
    );
  } finally {
    ledger.close();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "model check failed";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
