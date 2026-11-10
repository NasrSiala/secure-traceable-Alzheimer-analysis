import { Context } from "fabric-contract-api";

import { Provenance } from "../src/provenance";

const ARTIFACT_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_ID = "22222222-2222-4222-8222-222222222222";

class MemoryStub {
  readonly data = new Map<string, Buffer>();

  async getState(key: string): Promise<Uint8Array> {
    return this.data.get(key) ?? Buffer.alloc(0);
  }

  async putState(key: string, value: Uint8Array): Promise<void> {
    this.data.set(key, Buffer.from(value));
  }

  getDateTimestamp(): Date {
    return new Date("2026-11-09T18:00:00.000Z");
  }
}

interface Caller {
  role: string | null;
  agent: string | null;
  mspId: string;
  id: string;
}

const PIPELINE_AGENT: Caller = {
  role: "pipeline-agent",
  agent: "ingestion",
  mspId: "Org1MSP",
  id: "x509::/CN=agent-ingestion/OU=client::/CN=ca.org1.example.com",
};

class MemoryIdentity {
  constructor(private readonly caller: Caller) {}

  getAttributeValue(name: string): string | null {
    if (name === "role") {
      return this.caller.role;
    }
    if (name === "agent") {
      return this.caller.agent;
    }
    return null;
  }

  getMSPID(): string {
    return this.caller.mspId;
  }

  getID(): string {
    return this.caller.id;
  }
}

function context(caller: Caller = PIPELINE_AGENT): { ctx: Context; stub: MemoryStub } {
  const stub = new MemoryStub();
  const ctx = { stub, clientIdentity: new MemoryIdentity(caller) } as unknown as Context;
  return { ctx, stub };
}

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
    const { ctx } = context();
    await contract.CreateArtifactRecord(ctx, validBody());
    await expect(
      contract.CreateArtifactRecord(ctx, validBody({ sha256: "cd".repeat(32) })),
    ).rejects.toThrow("DUPLICATE");
    const stored = JSON.parse(await contract.GetArtifactRecord(ctx, ARTIFACT_ID)) as Record<
      string,
      unknown
    >;
    expect(stored.sha256).toBe("ab".repeat(32));
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
