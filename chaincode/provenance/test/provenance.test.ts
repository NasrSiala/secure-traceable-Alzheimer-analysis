import { Context } from "fabric-contract-api";

import { Provenance } from "../src/provenance";
import { context, MemoryIdentity, type MemoryStub, PIPELINE_AGENT } from "./memory-ledger";

const ARTIFACT_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_ID = "22222222-2222-4222-8222-222222222222";

function validObject(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    artifactId: ARTIFACT_ID,
    caseId: `CASE-${ARTIFACT_ID}`,
    artifactType: "original",
    sha256: "ab".repeat(32),
    createdAt: "2026-11-09T12:00:00.000Z",
    softwareVersion: "0.1.0",
    modelVersion: null,
    parentArtifactId: null,
    offchainRef: `artifact://${ARTIFACT_ID}`,
    ...overrides,
  };
}

function validBody(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify(validObject(overrides));
}

describe("CreateArtifactRecord", () => {
  const contract = new Provenance();

  test("stores a closed ARTIFACT and reads it back", async () => {
    const { ctx } = context();
    const created = JSON.parse(await contract.CreateArtifactRecord(ctx, validBody())) as Record<
      string,
      unknown
    >;
    expect(created).toMatchObject({
      docType: "artifact",
      artifactId: ARTIFACT_ID,
      artifactType: "original",
      sha256: "ab".repeat(32),
      txTimestamp: "2026-11-09T18:00:00.000Z",
      creatorMspId: "Org1MSP",
      creatorId: "/CN=agent-ingestion/OU=client",
      creatorAgent: "ingestion",
    });
    const read = JSON.parse(await contract.GetArtifactRecord(ctx, ARTIFACT_ID)) as Record<
      string,
      unknown
    >;
    expect(read).toEqual(created);
  });

  test("rejects a duplicate artifactId", async () => {
    const { ctx } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    await expect(contract.CreateArtifactRecord(ctx, validBody())).rejects.toThrow("DUPLICATE");
  });

  test("a duplicate never overwrites the stored record (AC-07.3)", async () => {
    const { ctx, stub } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ sha256: "cd".repeat(32) })),
    ).rejects.toThrow("DUPLICATE");
    const stored = JSON.parse(await contract.GetArtifactRecord(ctx, ARTIFACT_ID)) as Record<
      string,
      unknown
    >;
    expect(stored.sha256).toBe("ab".repeat(32));
    expect(stub.data.size).toBe(2);
    expect(stub.events).toHaveLength(1);
  });

  test("rejects an unknown field", async () => {
    const { ctx } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ patientName: "hidden" })),
    ).rejects.toThrow("SCHEMA");
  });

  test("rejects a client-supplied creator field", async () => {
    const { ctx } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ creatorMspId: "Org2MSP" })),
    ).rejects.toThrow("SCHEMA");
  });

  test.each(["docType", "txTimestamp", "creatorId", "creatorAgent", "__proto__"])(
    "rejects the chaincode-owned or reserved field %s from the client",
    async (field) => {
      const { ctx, stub } = context();
      const body = JSON.stringify(validObject()).replace(/}$/, `,${JSON.stringify(field)}:"x"}`);
      await expect(contract.CreateArtifactRecord(ctx, body)).rejects.toThrow("SCHEMA");
      expect(stub.data.size).toBe(0);
    },
  );

  test("rejects a malformed sha256", async () => {
    const { ctx } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ sha256: "AB".repeat(32) })),
    ).rejects.toThrow("SCHEMA");
  });

  test("rejects an artifactType outside the list", async () => {
    const { ctx } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ artifactType: "ecg" })),
    ).rejects.toThrow("SCHEMA");
  });

  test.each([
    "artifactId",
    "caseId",
    "artifactType",
    "sha256",
    "createdAt",
    "softwareVersion",
    "parentArtifactId",
    "offchainRef",
  ])("rejects a body without %s", async (field) => {
    const { ctx } = context();
    const body = validObject();
    delete body[field];
    await expect(contract.CreateArtifactRecord(ctx, JSON.stringify(body))).rejects.toThrow(
      "SCHEMA",
    );
  });

  test("modelVersion may be omitted and is stored as null", async () => {
    const { ctx } = context();
    const body = validObject();
    delete body.modelVersion;
    const created = JSON.parse(
      await contract.CreateArtifactRecord(ctx, JSON.stringify(body)),
    ) as Record<string, unknown>;
    expect(created.modelVersion).toBeNull();
  });

  test.each([
    ["softwareVersion", ""],
    ["softwareVersion", "x".repeat(65)],
    ["modelVersion", ""],
    ["modelVersion", "x".repeat(65)],
    ["modelVersion", 3],
  ])("rejects %s = %j", async (field, value) => {
    const { ctx } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ [field]: value })),
    ).rejects.toThrow("SCHEMA");
  });

  test("accepts a softwareVersion of exactly 64 characters", async () => {
    const { ctx } = context();
    const created = JSON.parse(
      await contract.CreateArtifactRecord(ctx, validBody({ softwareVersion: "x".repeat(64) })),
    ) as Record<string, unknown>;
    expect(created.softwareVersion).toBe("x".repeat(64));
  });

  test.each(["[]", "null", "42", '"text"', "{not json", ""])(
    "rejects a body that is not a JSON object: %j",
    async (body) => {
      const { ctx } = context();
      await expect(contract.CreateArtifactRecord(ctx, body)).rejects.toThrow("SCHEMA");
    },
  );

  test.each([
    ["artifactId", "AAAAAAAA-1111-4111-8111-111111111111"],
    ["artifactId", "not-a-uuid"],
    ["caseId", "case-11111111-1111-4111-8111-111111111111"],
    ["caseId", "CASE-short"],
    ["parentArtifactId", "not-a-uuid"],
    ["parentArtifactId", 7],
    ["offchainRef", `artifact://${OTHER_ID}`],
    ["offchainRef", "file:///etc/passwd"],
    ["createdAt", "2026-02-30T00:00:00Z"],
    ["createdAt", "2026-11-09T12:00:00"],
    ["createdAt", "2026-11-09T12:00:00+01:00"],
    ["createdAt", "yesterday"],
  ])("rejects %s = %j", async (field, value) => {
    const { ctx, stub } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ [field]: value })),
    ).rejects.toThrow("SCHEMA");
    expect(stub.data.size).toBe(0);
  });

  test("accepts createdAt without a fractional part", async () => {
    const { ctx } = context();
    const created = JSON.parse(
      await contract.CreateArtifactRecord(ctx, validBody({ createdAt: "2026-11-09T12:00:00Z" })),
    ) as Record<string, unknown>;
    expect(created.createdAt).toBe("2026-11-09T12:00:00Z");
  });
});

describe("caller authorization", () => {
  const contract = new Provenance();

  test.each([
    ["no role and no agent attribute", { role: null, agent: null }],
    ["role model-admin", { role: "model-admin", agent: null }],
    ["role model-admin with an agent attribute", { role: "model-admin", agent: "ingestion" }],
    ["role pipeline-agent without an agent attribute", { role: "pipeline-agent", agent: null }],
    ["role pipeline-agent with an empty agent attribute", { role: "pipeline-agent", agent: "" }],
  ])("refuses %s with FORBIDDEN and stores nothing", async (_label, attributes) => {
    const { ctx, stub } = context({ ...PIPELINE_AGENT, ...attributes });
    await expect(contract.CreateArtifactRecord(ctx, validBody())).rejects.toThrow("FORBIDDEN");
    expect(stub.data.size).toBe(0);
  });

  test("authorization comes before validation: an unauthorized caller learns nothing about the schema", async () => {
    const { ctx } = context({ ...PIPELINE_AGENT, role: null, agent: null });
    await expect(contract.CreateArtifactRecord(ctx, '{"patientName":"x"}')).rejects.toThrow(
      "FORBIDDEN",
    );
  });

  test("creator fields come from the caller, whatever organization it belongs to", async () => {
    const { ctx } = context({
      role: "pipeline-agent",
      agent: "prediction",
      mspId: "Org2MSP",
      id: "x509::/CN=agent-prediction/OU=client::/CN=ca.org2.example.com",
    });
    const created = JSON.parse(await contract.CreateArtifactRecord(ctx, validBody())) as Record<
      string,
      unknown
    >;
    expect(created).toMatchObject({
      creatorMspId: "Org2MSP",
      creatorId: "/CN=agent-prediction/OU=client",
      creatorAgent: "prediction",
    });
  });

  test("a caller whose certificate subject is unavailable is refused", async () => {
    const { ctx, stub } = context({ ...PIPELINE_AGENT, id: "not-an-x509-id" });
    await expect(contract.CreateArtifactRecord(ctx, validBody())).rejects.toThrow("SCHEMA");
    expect(stub.data.size).toBe(0);
  });

  test("reading needs no attribute", async () => {
    const { ctx, stub } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    const verifier = new MemoryIdentity({
      role: null,
      agent: null,
      mspId: "Org2MSP",
      id: "x509::/CN=verifier/OU=client::/CN=ca.org2.example.com",
    });
    const reader = { stub, clientIdentity: verifier } as unknown as Context;
    const read = JSON.parse(await contract.GetArtifactRecord(reader, ARTIFACT_ID)) as Record<
      string,
      unknown
    >;
    expect(read.artifactId).toBe(ARTIFACT_ID);
  });
});

describe("GetArtifactRecord", () => {
  const contract = new Provenance();

  test("reports an absent artifact as NOT_FOUND", async () => {
    const { ctx } = context();
    await expect(contract.GetArtifactRecord(ctx, OTHER_ID)).rejects.toThrow("NOT_FOUND");
  });

  test.each(["", "not-a-uuid", "AAAAAAAA-1111-4111-8111-111111111111", `${ARTIFACT_ID}x`])(
    "rejects the malformed id %j before touching the ledger",
    async (id) => {
      const { ctx } = context();
      await expect(contract.GetArtifactRecord(ctx, id)).rejects.toThrow("SCHEMA");
    },
  );
});

const HISTORY_CASE = "CASE-33333333-3333-4333-8333-333333333333";
const PIPELINE = [
  "original",
  "processed",
  "features",
  "prediction",
  "validation",
  "explanation",
  "final_result",
] as const;

function chainId(rank: number): string {
  const digit = 7 - rank;
  return `aaaaaaa${digit}-aaaa-4aaa-8aaa-aaaaaaaaaaa${digit}`;
}

function chainBody(rank: number, parent: string | null): string {
  const artifactId = chainId(rank);
  return JSON.stringify({
    artifactId,
    caseId: HISTORY_CASE,
    artifactType: PIPELINE[rank],
    sha256: "ab".repeat(32),
    createdAt: "2026-11-09T12:00:00.000Z",
    softwareVersion: "0.1.0",
    modelVersion: null,
    parentArtifactId: parent,
    offchainRef: `artifact://${artifactId}`,
  });
}

describe("parent rules", () => {
  const contract = new Provenance();

  test("refuses a parent that is not on the ledger", async () => {
    const { ctx, stub } = context();
    await expect(
      contract.CreateArtifactRecord(
        ctx,
        validBody({
          artifactId: OTHER_ID,
          artifactType: "processed",
          parentArtifactId: ARTIFACT_ID,
          offchainRef: `artifact://${OTHER_ID}`,
        }),
      ),
    ).rejects.toThrow("PARENT_MISSING");
    expect(stub.data.size).toBe(0);
    expect(stub.events).toEqual([]);
  });

  test("refuses a parent from another case", async () => {
    const { ctx, stub } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    const childId = "33333333-3333-4333-8333-333333333333";
    await expect(
      contract.CreateArtifactRecord(
        ctx,
        validBody({
          artifactId: childId,
          caseId: "CASE-22222222-2222-4222-8222-222222222222",
          artifactType: "processed",
          parentArtifactId: ARTIFACT_ID,
          offchainRef: `artifact://${childId}`,
        }),
      ),
    ).rejects.toThrow("PARENT_MISSING");
    expect(stub.data.size).toBe(2);
    expect(stub.events).toHaveLength(1);
  });

  test("refuses a non-original record with a null parent", async () => {
    const { ctx, stub } = context();
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ artifactType: "processed" })),
    ).rejects.toThrow("PARENT_MISSING");
    expect(stub.data.size).toBe(0);
    expect(stub.events).toEqual([]);
  });

  test("refuses an original record that names a parent", async () => {
    const { ctx, stub } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    await expect(
      contract.CreateArtifactRecord(
        ctx,
        validBody({
          artifactId: OTHER_ID,
          artifactType: "original",
          parentArtifactId: ARTIFACT_ID,
          offchainRef: `artifact://${OTHER_ID}`,
        }),
      ),
    ).rejects.toThrow("SCHEMA");
    expect(stub.events).toHaveLength(1);
    await expect(contract.GetArtifactRecord(ctx, OTHER_ID)).rejects.toThrow("NOT_FOUND");
  });

  test("a duplicate stays DUPLICATE when the second body would also fail the parent rule", async () => {
    const { ctx } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ artifactType: "processed" })),
    ).rejects.toThrow("DUPLICATE");
  });

  test("emits ArtifactAnchored with the stored record, not with client creator fields", async () => {
    const { ctx, stub } = context();
    const request = validBody();
    const created = await contract.CreateArtifactRecord(ctx, request);
    expect(request.includes("creatorMspId")).toBe(false);
    expect(request.includes("creatorId")).toBe(false);
    expect(request.includes("creatorAgent")).toBe(false);
    expect(stub.events).toEqual([{ name: "ArtifactAnchored", payload: Buffer.from(created) }]);
    const payload = JSON.parse(created) as Record<string, unknown>;
    expect(payload).toMatchObject({
      creatorMspId: "Org1MSP",
      creatorId: "/CN=agent-ingestion/OU=client",
      creatorAgent: "ingestion",
      txTimestamp: "2026-11-09T18:00:00.000Z",
    });
    const index = stub.createCompositeKey("case~artifact", [`CASE-${ARTIFACT_ID}`, ARTIFACT_ID]);
    expect(index.startsWith("\u0000case~artifact\u0000")).toBe(true);
    expect(stub.data.get(index)?.toString("utf8")).toBe(ARTIFACT_ID);
  });
});

describe("GetCaseHistory", () => {
  const contract = new Provenance();

  test("returns an empty history when the case has no artifacts", async () => {
    const { ctx } = context();
    expect(await contract.GetCaseHistory(ctx, HISTORY_CASE)).toBe("[]");
  });

  test.each(["case-short", "CASE-SHORT", "CASE-33333333-3333-4333-8333-33333333333"])(
    "rejects the malformed case id %j",
    async (caseId) => {
      const { ctx } = context();
      await expect(contract.GetCaseHistory(ctx, caseId)).rejects.toThrow("SCHEMA");
    },
  );

  test("returns seven records parent to child even when their keys sort the other way", async () => {
    const { ctx, stub } = context();
    for (let rank = 0; rank < PIPELINE.length; rank += 1) {
      const parent = rank === 0 ? null : chainId(rank - 1);
      await contract.CreateArtifactRecord(ctx, chainBody(rank, parent));
    }
    const verifier = new MemoryIdentity({
      role: null,
      agent: null,
      mspId: "Org2MSP",
      id: "x509::/CN=verifier/OU=client::/CN=ca.org2.example.com",
    });
    const reader = { stub, clientIdentity: verifier } as unknown as Context;
    const history = JSON.parse(await contract.GetCaseHistory(reader, HISTORY_CASE)) as Record<
      string,
      unknown
    >[];
    expect(history.map((record) => record.artifactType)).toEqual([...PIPELINE]);
    expect(history.map((record) => record.artifactId)).toEqual(
      PIPELINE.map((_, rank) => chainId(rank)),
    );
    expect(history[0]?.parentArtifactId).toBeNull();
    for (let rank = 1; rank < history.length; rank += 1) {
      expect(history[rank]?.parentArtifactId).toBe(chainId(rank - 1));
    }
    expect(history.every((record) => record.txTimestamp === "2026-11-09T18:00:00.000Z")).toBe(true);
    expect(history.every((record) => record.creatorAgent === "ingestion")).toBe(true);
    expect(stub.events).toHaveLength(PIPELINE.length);
    expect(stub.events.every((event) => event.name === "ArtifactAnchored")).toBe(true);
  });
});

const OTHER_CASE = "CASE-44444444-4444-4444-8444-444444444444";

function chainObject(
  artifactId: string,
  artifactType: string,
  parent: string | null,
  caseId: string = HISTORY_CASE,
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
  });
}

async function history(
  contract: Provenance,
  ctx: Context,
  caseId: string = HISTORY_CASE,
): Promise<string[]> {
  const records = JSON.parse(await contract.GetCaseHistory(ctx, caseId)) as {
    artifactId: string;
  }[];
  return records.map((record) => record.artifactId);
}

describe("GetCaseHistory: case isolation and branching", () => {
  const contract = new Provenance();
  const ROOT = "bbbbbbb1-bbbb-4bbb-8bbb-bbbbbbbbbbb1";
  const LATER_BUT_FIRST_BY_ID = "aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaa1";
  const EARLIER_BUT_LAST_BY_ID = "ccccccc1-cccc-4ccc-8ccc-ccccccccccc1";
  const GRANDCHILD = "ddddddd1-dddd-4ddd-8ddd-ddddddddddd1";

  test("lists only the artifacts of the case asked for", async () => {
    const { ctx } = context();
    await contract.CreateArtifactRecord(ctx, chainObject(ROOT, "original", null));
    await contract.CreateArtifactRecord(ctx, chainObject(LATER_BUT_FIRST_BY_ID, "processed", ROOT));
    await contract.CreateArtifactRecord(ctx, chainObject(OTHER_ID, "original", null, OTHER_CASE));
    await contract.CreateArtifactRecord(
      ctx,
      chainObject(ARTIFACT_ID, "original", null, `CASE-${ARTIFACT_ID}`),
    );

    expect(await history(contract, ctx)).toEqual([ROOT, LATER_BUT_FIRST_BY_ID]);
    expect(await history(contract, ctx, OTHER_CASE)).toEqual([OTHER_ID]);
    expect(await history(contract, ctx, `CASE-${ARTIFACT_ID}`)).toEqual([ARTIFACT_ID]);
    expect(await history(contract, ctx, "CASE-55555555-5555-4555-8555-555555555555")).toEqual([]);
  });

  test("siblings come in the order the ledger recorded them, not in id order", async () => {
    const { ctx, stub } = context();
    await contract.CreateArtifactRecord(ctx, chainObject(ROOT, "original", null));
    stub.now = "2026-11-09T18:00:02.000Z";
    await contract.CreateArtifactRecord(ctx, chainObject(LATER_BUT_FIRST_BY_ID, "processed", ROOT));
    stub.now = "2026-11-09T18:00:01.000Z";
    await contract.CreateArtifactRecord(ctx, chainObject(EARLIER_BUT_LAST_BY_ID, "features", ROOT));

    expect(await history(contract, ctx)).toEqual([
      ROOT,
      EARLIER_BUT_LAST_BY_ID,
      LATER_BUT_FIRST_BY_ID,
    ]);
  });

  test("equal timestamps fall back to the artifact id, so the answer never varies", async () => {
    const { ctx } = context();
    await contract.CreateArtifactRecord(ctx, chainObject(ROOT, "original", null));
    await contract.CreateArtifactRecord(ctx, chainObject(EARLIER_BUT_LAST_BY_ID, "features", ROOT));
    await contract.CreateArtifactRecord(ctx, chainObject(LATER_BUT_FIRST_BY_ID, "processed", ROOT));

    expect(await history(contract, ctx)).toEqual([
      ROOT,
      LATER_BUT_FIRST_BY_ID,
      EARLIER_BUT_LAST_BY_ID,
    ]);
  });

  test("a child never comes before its parent, even when an agent clock runs behind", async () => {
    const { ctx, stub } = context();
    stub.now = "2026-11-09T18:00:10.000Z";
    await contract.CreateArtifactRecord(ctx, chainObject(ROOT, "original", null));
    stub.now = "2026-11-09T18:00:20.000Z";
    await contract.CreateArtifactRecord(ctx, chainObject(LATER_BUT_FIRST_BY_ID, "processed", ROOT));
    stub.now = "2026-11-09T18:00:05.000Z";
    await contract.CreateArtifactRecord(
      ctx,
      chainObject(GRANDCHILD, "features", LATER_BUT_FIRST_BY_ID),
    );

    expect(await history(contract, ctx)).toEqual([ROOT, LATER_BUT_FIRST_BY_ID, GRANDCHILD]);
  });
});

describe("a ledger state that cannot be read back is INTEGRITY, not a caller error", () => {
  const contract = new Provenance();
  const ROOT = "bbbbbbb1-bbbb-4bbb-8bbb-bbbbbbbbbbb1";
  const CHILD = "aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaa1";

  async function withRoot(): Promise<{ ctx: Context; stub: MemoryStub }> {
    const made = context();
    await contract.CreateArtifactRecord(made.ctx, chainObject(ROOT, "original", null));
    return made;
  }

  async function rewrite(
    stub: MemoryStub,
    id: string,
    change: (record: Record<string, unknown>) => void,
  ): Promise<void> {
    const stored = JSON.parse((await stub.getState(id)).toString()) as Record<string, unknown>;
    change(stored);
    await stub.putState(id, Buffer.from(JSON.stringify(stored)));
  }

  test("an index entry whose record is gone", async () => {
    const { ctx, stub } = await withRoot();
    stub.data.delete(ROOT);

    await expect(contract.GetCaseHistory(ctx, HISTORY_CASE)).rejects.toThrow(
      "INTEGRITY: an indexed artifact is not on the ledger",
    );
  });

  test("an index entry that points into another case", async () => {
    const { ctx, stub } = await withRoot();
    await contract.CreateArtifactRecord(ctx, chainObject(OTHER_ID, "original", null, OTHER_CASE));
    const index = stub.createCompositeKey("case~artifact", [HISTORY_CASE, OTHER_ID]);
    await stub.putState(index, Buffer.from(OTHER_ID));

    await expect(contract.GetCaseHistory(ctx, HISTORY_CASE)).rejects.toThrow(
      "INTEGRITY: an indexed artifact belongs to another case",
    );
  });

  test.each([
    ["is not JSON", "not json"],
    ["is a JSON array", "[]"],
    ["has no docType", JSON.stringify({ artifactId: ROOT, caseId: HISTORY_CASE })],
    [
      "has no caseId",
      JSON.stringify({
        docType: "artifact",
        artifactId: ROOT,
        txTimestamp: "2026-11-09T18:00:00.000Z",
        parentArtifactId: null,
      }),
    ],
    [
      "has no artifactId",
      JSON.stringify({
        docType: "artifact",
        caseId: HISTORY_CASE,
        txTimestamp: "2026-11-09T18:00:00.000Z",
        parentArtifactId: null,
      }),
    ],
    [
      "has another docType",
      JSON.stringify({
        docType: "model",
        artifactId: ROOT,
        caseId: HISTORY_CASE,
        txTimestamp: "2026-11-09T18:00:00.000Z",
        parentArtifactId: null,
      }),
    ],
    [
      "has no transaction timestamp",
      JSON.stringify({
        docType: "artifact",
        artifactId: ROOT,
        caseId: HISTORY_CASE,
        parentArtifactId: null,
      }),
    ],
    [
      "has a parent that is not a string or null",
      JSON.stringify({
        docType: "artifact",
        artifactId: ROOT,
        caseId: HISTORY_CASE,
        txTimestamp: "2026-11-09T18:00:00.000Z",
        parentArtifactId: 7,
      }),
    ],
  ])("a stored parent that %s fails the create and stores nothing", async (_label, stored) => {
    const { ctx, stub } = await withRoot();
    await stub.putState(ROOT, Buffer.from(stored));
    const before = stub.data.size;

    await expect(
      contract.CreateArtifactRecord(ctx, chainObject(CHILD, "processed", ROOT)),
    ).rejects.toThrow("INTEGRITY");
    expect(stub.data.size).toBe(before);
    expect(stub.events).toHaveLength(1);
  });

  test("a stored record that is corrupt fails the single read", async () => {
    const { ctx, stub } = await withRoot();
    await stub.putState(ROOT, Buffer.from("not json"));

    await expect(contract.GetArtifactRecord(ctx, ROOT)).rejects.toThrow(
      "INTEGRITY: a stored record is not valid JSON",
    );
  });

  test("a stored record that is corrupt fails the history", async () => {
    const { ctx, stub } = await withRoot();
    await stub.putState(ROOT, Buffer.from("not json"));

    await expect(contract.GetCaseHistory(ctx, HISTORY_CASE)).rejects.toThrow(
      "INTEGRITY: a stored record is not valid JSON",
    );
  });

  test("a case whose record names a parent that is not there", async () => {
    const { ctx, stub } = await withRoot();
    await contract.CreateArtifactRecord(ctx, chainObject(CHILD, "processed", ROOT));
    await rewrite(stub, CHILD, (record) => {
      record.parentArtifactId = OTHER_ID;
    });

    await expect(contract.GetCaseHistory(ctx, HISTORY_CASE)).rejects.toThrow(
      "INTEGRITY: a case holds an artifact whose parent is missing or that is in a cycle",
    );
  });

  test("a case whose records name each other as parent", async () => {
    const { ctx, stub } = await withRoot();
    await contract.CreateArtifactRecord(ctx, chainObject(CHILD, "processed", ROOT));
    await rewrite(stub, ROOT, (record) => {
      record.parentArtifactId = CHILD;
    });

    await expect(contract.GetCaseHistory(ctx, HISTORY_CASE)).rejects.toThrow("INTEGRITY");
  });
});
