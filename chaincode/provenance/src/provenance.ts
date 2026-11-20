import { Context, Contract, Info, Transaction } from "fabric-contract-api";

import {
  type ArtifactRecord,
  type CallerIdentity,
  certificateSubject,
  SHA256,
  parseClientArtifact,
  requireCaseId,
  requirePipelineAgent,
  requireUuid,
} from "./artifact";
import { fail } from "./errors";
import {
  MODEL_KEY,
  type ModelRecord,
  parseClientModel,
  requireModelAdmin,
  requireModelName,
  requireModelVersion,
} from "./model";

const CASE_ARTIFACT = "case~artifact";
const ARTIFACT_ANCHORED = "ArtifactAnchored";

type Stub = Context["stub"];
type ClientArtifact = ReturnType<typeof parseClientArtifact>;

function callerOf(ctx: Context): CallerIdentity {
  return {
    mspId: ctx.clientIdentity.getMSPID(),
    subject: certificateSubject(ctx.clientIdentity.getID()),
    role: ctx.clientIdentity.getAttributeValue("role"),
    agent: ctx.clientIdentity.getAttributeValue("agent"),
  };
}

function isStoredArtifact(value: unknown): value is ArtifactRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    record.docType === "artifact" &&
    typeof record.artifactId === "string" &&
    typeof record.caseId === "string" &&
    typeof record.txTimestamp === "string" &&
    (record.parentArtifactId === null || typeof record.parentArtifactId === "string")
  );
}

// What the ledger holds is the chaincode's own output. A record that cannot be read back is a
// fault of the ledger state, not of the caller: INTEGRITY, never SCHEMA or NOT_FOUND.
function parseStoredModel(raw: Uint8Array): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(raw).toString("utf8")) as unknown;
  } catch {
    fail("INTEGRITY", "a stored record is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    fail("INTEGRITY", "a stored record is not a model");
  }
  const record = parsed as Record<string, unknown>;
  if (
    record.docType !== "model" ||
    typeof record.name !== "string" ||
    typeof record.version !== "string" ||
    typeof record.sha256 !== "string" ||
    !SHA256.test(record.sha256) ||
    typeof record.framework !== "string" ||
    record.framework.length < 1 ||
    record.framework.length > 40 ||
    typeof record.registeredAt !== "string" ||
    typeof record.registeredBy !== "string"
  ) {
    fail("INTEGRITY", "a stored record is not a model");
  }
}

function parseStoredArtifact(raw: Uint8Array): ArtifactRecord {
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(raw).toString("utf8")) as unknown;
  } catch {
    fail("INTEGRITY", "a stored record is not valid JSON");
  }
  if (!isStoredArtifact(parsed)) {
    fail("INTEGRITY", "a stored record is not an artifact");
  }
  return parsed;
}

async function requireParent(stub: Stub, client: ClientArtifact): Promise<void> {
  if (client.artifactType === "original") {
    if (client.parentArtifactId !== null) {
      fail("SCHEMA", "original must have a null parent");
    }
    return;
  }
  if (client.parentArtifactId === null) {
    fail("PARENT_MISSING", "parentArtifactId is required");
  }
  const raw = await stub.getState(client.parentArtifactId);
  if (raw.length === 0) {
    fail("PARENT_MISSING", "parentArtifactId does not exist in this case");
  }
  if (parseStoredArtifact(raw).caseId !== client.caseId) {
    fail("PARENT_MISSING", "parentArtifactId does not exist in this case");
  }
}

async function recordsForCase(stub: Stub, caseId: string): Promise<ArtifactRecord[]> {
  const iterator = await stub.getStateByPartialCompositeKey(CASE_ARTIFACT, [caseId]);
  const ids: string[] = [];
  try {
    for (;;) {
      const result = await iterator.next();
      if (result.done || result.value === undefined) {
        break;
      }
      if (result.value.value.length !== 0) {
        ids.push(Buffer.from(result.value.value).toString("utf8"));
      }
    }
  } finally {
    await iterator.close();
  }

  return Promise.all(
    ids.map(async (artifactId) => {
      const stored = await stub.getState(artifactId);
      if (stored.length === 0) {
        fail("INTEGRITY", "an indexed artifact is not on the ledger");
      }
      const record = parseStoredArtifact(stored);
      if (record.caseId !== caseId) {
        fail("INTEGRITY", "an indexed artifact belongs to another case");
      }
      return record;
    }),
  );
}

function compareChronologically(left: ArtifactRecord, right: ArtifactRecord): number {
  if (left.txTimestamp !== right.txTimestamp) {
    return left.txTimestamp < right.txTimestamp ? -1 : 1;
  }
  if (left.artifactId !== right.artifactId) {
    return left.artifactId < right.artifactId ? -1 : 1;
  }
  return 0;
}

// A child always comes after its parent. Among the artifacts that may come next, the one the
// ledger recorded first comes first (the artifact id only breaks a tie). Clocks of the agents
// can disagree, so the timestamp alone could put a child before its parent.
function orderParentToChild(records: ArtifactRecord[]): ArtifactRecord[] {
  const pending = [...records].sort(compareChronologically);
  const placed = new Set<string>();
  const ordered: ArtifactRecord[] = [];
  while (pending.length > 0) {
    const next = pending.findIndex(
      (record) => record.parentArtifactId === null || placed.has(record.parentArtifactId),
    );
    if (next === -1) {
      // CreateArtifactRecord only accepts a parent that already exists in the same case.
      fail("INTEGRITY", "a case holds an artifact whose parent is missing or that is in a cycle");
    }
    const [record] = pending.splice(next, 1);
    if (record === undefined) {
      continue;
    }
    placed.add(record.artifactId);
    ordered.push(record);
  }
  return ordered;
}

@Info({
  title: "Provenance",
  description: "Creates, reads, and lists closed-schema ARTIFACT records; registers and reads MODEL records",
})
export class Provenance extends Contract {
  @Transaction()
  public async CreateArtifactRecord(ctx: Context, json: string): Promise<string> {
    // Who may write comes first: a caller without the role learns nothing about the schema.
    const caller = callerOf(ctx);
    const creatorAgent = requirePipelineAgent(caller);
    const client = parseClientArtifact(json);
    const stub = ctx.stub;
    const existing = await stub.getState(client.artifactId);
    if (existing.length !== 0) {
      fail("DUPLICATE", "artifactId already exists");
    }
    await requireParent(stub, client);
    const record: ArtifactRecord = {
      docType: "artifact",
      ...client,
      txTimestamp: stub.getDateTimestamp().toISOString(),
      creatorMspId: caller.mspId,
      creatorId: caller.subject,
      creatorAgent,
    };
    const payload = JSON.stringify(record);
    await stub.putState(client.artifactId, Buffer.from(payload));
    await stub.putState(
      stub.createCompositeKey(CASE_ARTIFACT, [client.caseId, client.artifactId]),
      Buffer.from(client.artifactId),
    );
    stub.setEvent(ARTIFACT_ANCHORED, Buffer.from(payload));
    return payload;
  }

  @Transaction(false)
  public async GetArtifactRecord(ctx: Context, artifactId: string): Promise<string> {
    requireUuid(artifactId, "artifactId");
    const stored = await ctx.stub.getState(artifactId);
    if (stored.length === 0) {
      fail("NOT_FOUND", "artifactId is not on the ledger");
    }
    parseStoredArtifact(stored);
    return Buffer.from(stored).toString("utf8");
  }

  @Transaction(false)
  public async GetCaseHistory(ctx: Context, caseId: string): Promise<string> {
    requireCaseId(caseId);
    const records = await recordsForCase(ctx.stub, caseId);
    return JSON.stringify(orderParentToChild(records));
  }

  @Transaction()
  public async RegisterModel(ctx: Context, json: string): Promise<string> {
    // Same order as CreateArtifactRecord: the role first, so that a caller without it learns
    // nothing about the schema or about which models exist.
    const caller = callerOf(ctx);
    requireModelAdmin(caller);
    const client = parseClientModel(json);
    const stub = ctx.stub;
    const key = stub.createCompositeKey(MODEL_KEY, [client.name, client.version]);
    const existing = await stub.getState(key);
    if (existing.length !== 0) {
      fail("DUPLICATE", "model name and version already exist");
    }
    const record: ModelRecord = {
      docType: "model",
      ...client,
      registeredAt: stub.getDateTimestamp().toISOString(),
      registeredBy: caller.subject,
    };
    const payload = JSON.stringify(record);
    await stub.putState(key, Buffer.from(payload));
    return payload;
  }

  @Transaction(false)
  public async GetModel(ctx: Context, name: string, version: string): Promise<string> {
    requireModelName(name);
    requireModelVersion(version);
    const stored = await ctx.stub.getState(ctx.stub.createCompositeKey(MODEL_KEY, [name, version]));
    if (stored.length === 0) {
      fail("NOT_FOUND", "model is not on the ledger");
    }
    parseStoredModel(stored);
    return Buffer.from(stored).toString("utf8");
  }
}
