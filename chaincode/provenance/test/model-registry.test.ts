import { Context } from "fabric-contract-api";

import { Provenance } from "../src/provenance";
import { type Caller, context, MemoryIdentity, type MemoryStub } from "./memory-ledger";

// MODEL (Schema 5.2): key = composite key `model` (name, version); RegisterModel needs the
// certificate attribute role=model-admin (TRD 8.3, AC-04.3); GetModel is open to every identity.

const MODEL_ADMIN: Caller = {
  role: "model-admin",
  agent: null,
  mspId: "Org1MSP",
  id: "x509::/CN=model-admin/OU=client::/CN=ca.org1.example.com",
};

const VERIFIER: Caller = {
  role: null,
  agent: null,
  mspId: "Org2MSP",
  id: "x509::/CN=verifier/OU=client::/CN=ca.org2.example.com",
};

const SHA = "ab".repeat(32);
const ARTIFACT_ID = "11111111-1111-4111-8111-111111111111";

function modelObject(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "ecg-cnn",
    version: "1.0.0",
    sha256: SHA,
    framework: "pytorch",
    ...overrides,
  };
}

function modelBody(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify(modelObject(overrides));
}

function asCaller(stub: MemoryStub, caller: Caller): Context {
  return { stub, clientIdentity: new MemoryIdentity(caller) } as unknown as Context;
}

// The error contract is "<CODE>: <detail>": the code must lead the message, not just appear.
async function expectCode(attempt: Promise<unknown>, code: string): Promise<void> {
  await expect(attempt).rejects.toThrow(new RegExp(`^${code}: `));
}

function parsed(json: string): Record<string, unknown> {
  return JSON.parse(json) as Record<string, unknown>;
}

describe("the contract exposes RegisterModel and GetModel next to the artifact transactions", () => {
  test("five transactions: three submit and evaluate pairs as TRD 8.2 lists them", () => {
    const transactions = Reflect.getMetadata("fabric:transactions", Provenance.prototype) as {
      name: string;
      tag: string[];
      parameters: { name: string }[];
    }[];
    const summary = Object.fromEntries(
      transactions.map((transaction) => [
        transaction.name,
        {
          kind: transaction.tag.includes("SUBMIT") ? "submit" : "evaluate",
          parameters: transaction.parameters.map((parameter) => parameter.name),
        },
      ]),
    );
    expect(summary).toEqual({
      CreateArtifactRecord: { kind: "submit", parameters: ["json"] },
      GetArtifactRecord: { kind: "evaluate", parameters: ["artifactId"] },
      GetCaseHistory: { kind: "evaluate", parameters: ["caseId"] },
      RegisterModel: { kind: "submit", parameters: ["json"] },
      GetModel: { kind: "evaluate", parameters: ["name", "version"] },
    });
  });
});

describe("RegisterModel", () => {
  const contract = new Provenance();

  test("stores a closed MODEL and GetModel reads the same record back", async () => {
    const { ctx } = context(MODEL_ADMIN);
    const created = parsed(await contract.RegisterModel(ctx, modelBody()));
    expect(created).toEqual({
      docType: "model",
      name: "ecg-cnn",
      version: "1.0.0",
      sha256: SHA,
      framework: "pytorch",
      registeredAt: "2026-11-09T18:00:00.000Z",
      registeredBy: "/CN=model-admin/OU=client",
    });
    expect(parsed(await contract.GetModel(ctx, "ecg-cnn", "1.0.0"))).toEqual(created);
  });

  test("the key is the composite key `model` (name, version), and nothing else is written", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    const key = stub.createCompositeKey("model", ["ecg-cnn", "1.0.0"]);
    expect(key).toBe("\u0000model\u0000ecg-cnn\u00001.0.0\u0000");
    expect([...stub.data.keys()]).toEqual([key]);
    expect(parsed(stub.data.get(key)?.toString("utf8") ?? "{}").docType).toBe("model");
  });

  test("registeredAt and registeredBy come from the transaction and the certificate", async () => {
    const { ctx, stub } = context({
      ...MODEL_ADMIN,
      mspId: "Org2MSP",
      id: "x509::/CN=another-admin/OU=client::/CN=ca.org2.example.com",
    });
    stub.now = "2026-11-10T08:30:00.000Z";
    const created = parsed(await contract.RegisterModel(ctx, modelBody()));
    expect(created.registeredAt).toBe("2026-11-10T08:30:00.000Z");
    expect(created.registeredBy).toBe("/CN=another-admin/OU=client");
  });

  test("rejects a duplicate name and version with DUPLICATE and never overwrites", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    stub.now = "2026-11-10T09:00:00.000Z";
    await expectCode(
      contract.RegisterModel(ctx, modelBody({ sha256: "cd".repeat(32), framework: "onnx" })),
      "DUPLICATE",
    );
    const stored = parsed(await contract.GetModel(ctx, "ecg-cnn", "1.0.0"));
    expect(stored).toMatchObject({
      sha256: SHA,
      framework: "pytorch",
      registeredAt: "2026-11-09T18:00:00.000Z",
    });
    expect(stub.data.size).toBe(1);
  });

  test("a duplicate stays DUPLICATE when the same body is sent twice, as it would be by a retry", async () => {
    const { ctx } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    await expectCode(contract.RegisterModel(ctx, modelBody()), "DUPLICATE");
  });

  test("another version of the same name, and the same version of another name, are new models", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    await contract.RegisterModel(ctx, modelBody({ version: "1.0.1", sha256: "cd".repeat(32) }));
    await contract.RegisterModel(ctx, modelBody({ name: "ecg-cnn-small", sha256: "ef".repeat(32) }));
    expect(stub.data.size).toBe(3);
    expect(parsed(await contract.GetModel(ctx, "ecg-cnn", "1.0.1")).sha256).toBe("cd".repeat(32));
    expect(parsed(await contract.GetModel(ctx, "ecg-cnn-small", "1.0.0")).sha256).toBe(
      "ef".repeat(32),
    );
    expect(parsed(await contract.GetModel(ctx, "ecg-cnn", "1.0.0")).sha256).toBe(SHA);
  });
});

describe("RegisterModel authorization: role=model-admin and nothing else", () => {
  const contract = new Provenance();

  test.each([
    ["no attribute at all (verifier)", VERIFIER],
    ["role pipeline-agent", { ...MODEL_ADMIN, role: "pipeline-agent", agent: "ingestion" }],
    ["role pipeline-agent without an agent attribute", { ...MODEL_ADMIN, role: "pipeline-agent" }],
    ["a role in another letter case, Model-Admin", { ...MODEL_ADMIN, role: "Model-Admin" }],
    ["a role with a trailing space", { ...MODEL_ADMIN, role: "model-admin " }],
    ["a role that only starts with model-admin", { ...MODEL_ADMIN, role: "model-admin-2" }],
    ["role admin", { ...MODEL_ADMIN, role: "admin" }],
    ["an empty role", { ...MODEL_ADMIN, role: "" }],
  ])("refuses %s with FORBIDDEN and stores nothing", async (_label, caller) => {
    const { ctx, stub } = context(caller);
    await expectCode(contract.RegisterModel(ctx, modelBody()), "FORBIDDEN");
    expect(stub.data.size).toBe(0);
  });

  test("a model-admin with an agent attribute is still a model-admin", async () => {
    const { ctx } = context({ ...MODEL_ADMIN, agent: "ingestion" });
    const created = parsed(await contract.RegisterModel(ctx, modelBody()));
    expect(created.docType).toBe("model");
  });

  test("authorization comes before validation: an unauthorized caller learns nothing about the schema", async () => {
    const { ctx } = context(VERIFIER);
    await expectCode(contract.RegisterModel(ctx, '{"patientName":"x"}'), "FORBIDDEN");
    await expectCode(contract.RegisterModel(ctx, "{not json"), "FORBIDDEN");
  });

  test("authorization comes before the duplicate check: a refused caller cannot probe which models exist", async () => {
    const { stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(asCaller(stub, MODEL_ADMIN), modelBody());
    await expectCode(contract.RegisterModel(asCaller(stub, VERIFIER), modelBody()), "FORBIDDEN");
  });

  test("a model-admin cannot write an artifact, and a pipeline-agent cannot register a model", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await expectCode(contract.CreateArtifactRecord(ctx, "{}"), "FORBIDDEN");
    await expectCode(
      contract.RegisterModel(asCaller(stub, { ...MODEL_ADMIN, role: "pipeline-agent" }), modelBody()),
      "FORBIDDEN",
    );
    expect(stub.data.size).toBe(0);
  });

  test("a caller whose certificate subject is unavailable is refused and nothing is stored", async () => {
    const { ctx, stub } = context({ ...MODEL_ADMIN, id: "not-an-x509-id" });
    await expectCode(contract.RegisterModel(ctx, modelBody()), "SCHEMA");
    expect(stub.data.size).toBe(0);
  });
});

describe("RegisterModel closed schema", () => {
  const contract = new Provenance();

  test("rejects an unknown field", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await expectCode(contract.RegisterModel(ctx, modelBody({ patientName: "hidden" })), "SCHEMA");
    expect(stub.data.size).toBe(0);
  });

  // The first three belong to the chaincode; the next three are columns of the `models` table
  // that Schema 5.2 does not put on the chain.
  test.each([
    "docType",
    "registeredAt",
    "registeredBy",
    "filePath",
    "file_path",
    "metrics",
    "isActive",
    "is_active",
    "__proto__",
  ])("rejects the chaincode-owned, off-chain or reserved field %s from the client", async (field) => {
    const { ctx, stub } = context(MODEL_ADMIN);
    const body = JSON.stringify(modelObject()).replace(/}$/, `,${JSON.stringify(field)}:"x"}`);
    await expectCode(contract.RegisterModel(ctx, body), "SCHEMA");
    expect(stub.data.size).toBe(0);
  });

  test.each(["name", "version", "sha256", "framework"])(
    "rejects a body without %s",
    async (field) => {
      const { ctx, stub } = context(MODEL_ADMIN);
      const body = modelObject();
      delete body[field];
      await expectCode(contract.RegisterModel(ctx, JSON.stringify(body)), "SCHEMA");
      expect(stub.data.size).toBe(0);
    },
  );

  test.each(["[]", "null", "42", '"text"', "{not json", ""])(
    "rejects a body that is not a JSON object: %j",
    async (body) => {
      const { ctx, stub } = context(MODEL_ADMIN);
      await expectCode(contract.RegisterModel(ctx, body), "SCHEMA");
      expect(stub.data.size).toBe(0);
    },
  );

  test.each([
    ["name", ""],
    ["name", "ECG"],
    ["name", "ecg cnn"],
    ["name", "ecg/cnn"],
    ["name", "ecg.cnn"],
    ["name", "ecg-cnn\n"],
    ["name", "ecg\u0000cnn"],
    ["name", "é"],
    ["name", "x".repeat(61)],
    ["name", 7],
    ["name", null],
    ["version", ""],
    ["version", "1.0"],
    ["version", "v1.0.0"],
    ["version", "1.0.0-rc1"],
    ["version", "1.0.0.0"],
    ["version", "1.0.x"],
    ["version", "1.0.0\n"],
    ["version", " 1.0.0"],
    ["version", 1],
    ["version", null],
    ["sha256", "AB".repeat(32)],
    ["sha256", "ab".repeat(31)],
    ["sha256", `${"ab".repeat(32)}0`],
    ["sha256", `${"ab".repeat(31)}zz`],
    ["sha256", `${SHA}\n`],
    ["sha256", 7],
    ["sha256", null],
    ["framework", ""],
    ["framework", "x".repeat(41)],
    ["framework", 3],
    ["framework", null],
  ])("rejects %s = %j", async (field, value) => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await expectCode(contract.RegisterModel(ctx, modelBody({ [field]: value })), "SCHEMA");
    expect(stub.data.size).toBe(0);
  });

  test.each([
    ["name", "x".repeat(60)],
    ["name", "a"],
    ["name", "ecg_cnn-2"],
    ["name", ARTIFACT_ID],
    ["version", "0.0.0"],
    ["version", "10.200.3000"],
    ["framework", "x".repeat(40)],
    ["framework", "p"],
  ])("accepts %s = %j", async (field, value) => {
    const { ctx } = context(MODEL_ADMIN);
    const created = parsed(await contract.RegisterModel(ctx, modelBody({ [field]: value })));
    expect(created[field]).toBe(value);
  });
});

describe("GetModel", () => {
  const contract = new Provenance();

  test("a stored model that is not JSON is INTEGRITY", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    const key = stub.createCompositeKey("model", ["ecg-cnn", "1.0.0"]);
    await stub.putState(key, Buffer.from("not json"));

    await expectCode(contract.GetModel(ctx, "ecg-cnn", "1.0.0"), "INTEGRITY");
  });

  test("a stored object missing sha256 and framework is INTEGRITY", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    const key = stub.createCompositeKey("model", ["ecg-cnn", "1.0.0"]);
    await stub.putState(
      key,
      Buffer.from(
        JSON.stringify({
          docType: "model",
          name: "a",
          version: "1.0.0",
          registeredAt: "t",
          registeredBy: "x",
        }),
      ),
    );

    await expectCode(contract.GetModel(ctx, "ecg-cnn", "1.0.0"), "INTEGRITY");
  });

  test("a stored model whose sha256 or framework is not the written shape is INTEGRITY", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    const key = stub.createCompositeKey("model", ["ecg-cnn", "1.0.0"]);
    const sha = "ab".repeat(32);
    await stub.putState(
      key,
      Buffer.from(
        JSON.stringify({
          docType: "model",
          name: "ecg-cnn",
          version: "1.0.0",
          sha256: "abc",
          framework: "keras",
          registeredAt: "t",
          registeredBy: "x",
        }),
      ),
    );
    await expectCode(contract.GetModel(ctx, "ecg-cnn", "1.0.0"), "INTEGRITY");

    await stub.putState(
      key,
      Buffer.from(
        JSON.stringify({
          docType: "model",
          name: "ecg-cnn",
          version: "1.0.0",
          sha256: sha,
          framework: "k".repeat(41),
          registeredAt: "t",
          registeredBy: "x",
        }),
      ),
    );
    await expectCode(contract.GetModel(ctx, "ecg-cnn", "1.0.0"), "INTEGRITY");
  });

  test("reports an absent model as NOT_FOUND, a typed error", async () => {
    const { ctx } = context(MODEL_ADMIN);
    await expectCode(contract.GetModel(ctx, "ecg-cnn", "1.0.0"), "NOT_FOUND");
  });

  test("an absent version of a known name, and a known version of an absent name, are NOT_FOUND", async () => {
    const { ctx } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    await expectCode(contract.GetModel(ctx, "ecg-cnn", "2.0.0"), "NOT_FOUND");
    await expectCode(contract.GetModel(ctx, "other-model", "1.0.0"), "NOT_FOUND");
  });

  test("reading needs no attribute and no particular organization", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    const read = parsed(await contract.GetModel(asCaller(stub, VERIFIER), "ecg-cnn", "1.0.0"));
    expect(read).toMatchObject({ docType: "model", name: "ecg-cnn", sha256: SHA });
  });

  test("reading changes nothing on the ledger", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    const dataBefore = new Map(stub.data);
    const eventsBefore = [...stub.events];
    await contract.GetModel(ctx, "ecg-cnn", "1.0.0");
    await expectCode(contract.GetModel(ctx, "ecg-cnn", "9.9.9"), "NOT_FOUND");
    expect(stub.data).toEqual(dataBefore);
    expect(stub.events).toEqual(eventsBefore);
  });

  // A name that cannot be registered is refused as SCHEMA before the ledger is touched. The
  // null byte matters most: the real stub throws an untyped error on it.
  test.each([
    ["", "1.0.0"],
    ["ECG", "1.0.0"],
    ["ecg-cnn", ""],
    ["ecg-cnn", "1.0"],
    ["ecg-cnn", "latest"],
    ["ecg\u0000cnn", "1.0.0"],
    ["ecg-cnn", "1.0.0\u0000"],
    ["x".repeat(61), "1.0.0"],
  ])("rejects the lookup %j, %j as SCHEMA", async (name, version) => {
    const { ctx } = context(MODEL_ADMIN);
    await expectCode(contract.GetModel(ctx, name, version), "SCHEMA");
  });
});

describe("MODEL and ARTIFACT do not touch each other", () => {
  const contract = new Provenance();
  const CASE = `CASE-${ARTIFACT_ID}`;

  function artifactBody(): string {
    return JSON.stringify({
      artifactId: ARTIFACT_ID,
      caseId: CASE,
      artifactType: "original",
      sha256: SHA,
      createdAt: "2026-11-09T12:00:00.000Z",
      softwareVersion: "0.1.0",
      modelVersion: null,
      parentArtifactId: null,
      offchainRef: `artifact://${ARTIFACT_ID}`,
    });
  }

  test("a model named like an artifact id does not shadow the artifact, nor the other way round", async () => {
    const { stub } = context(MODEL_ADMIN);
    const admin = asCaller(stub, MODEL_ADMIN);
    const agent = asCaller(stub, { ...MODEL_ADMIN, role: "pipeline-agent", agent: "ingestion" });

    await contract.RegisterModel(admin, modelBody({ name: ARTIFACT_ID }));
    await expectCode(contract.GetArtifactRecord(agent, ARTIFACT_ID), "NOT_FOUND");

    await contract.CreateArtifactRecord(agent, artifactBody());
    expect(parsed(await contract.GetArtifactRecord(agent, ARTIFACT_ID)).docType).toBe("artifact");
    expect(parsed(await contract.GetModel(agent, ARTIFACT_ID, "1.0.0")).docType).toBe("model");
  });

  test("a registered model does not appear in any case history, and an artifact is not a model", async () => {
    const { stub } = context(MODEL_ADMIN);
    const admin = asCaller(stub, MODEL_ADMIN);
    const agent = asCaller(stub, { ...MODEL_ADMIN, role: "pipeline-agent", agent: "ingestion" });

    await contract.RegisterModel(admin, modelBody());
    expect(await contract.GetCaseHistory(admin, CASE)).toBe("[]");

    await contract.CreateArtifactRecord(agent, artifactBody());
    const history = JSON.parse(await contract.GetCaseHistory(admin, CASE)) as { docType: string }[];
    expect(history.map((record) => record.docType)).toEqual(["artifact"]);
    await expectCode(contract.GetModel(admin, "original", "0.1.0"), "NOT_FOUND");
  });

  test("registering a model emits no ArtifactAnchored event", async () => {
    const { ctx, stub } = context(MODEL_ADMIN);
    await contract.RegisterModel(ctx, modelBody());
    expect(stub.events.filter((event) => event.name === "ArtifactAnchored")).toEqual([]);
  });
});
