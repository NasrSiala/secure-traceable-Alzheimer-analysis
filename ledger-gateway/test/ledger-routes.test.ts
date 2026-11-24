import type { FastifyInstance } from "fastify";

import { buildApp } from "../src/app";
import { type FailureReport, isErrorEnvelope } from "../src/errors";
import type { LedgerSession } from "../src/fabric-client";
import { TokenDirectory } from "../src/tokens";
import { call, callRaw, codeOf, evaluateRefusal, submitRefusal } from "./ledger-fixtures";

// T2.6 (2/2): GET /ledger/cases/{caseId}, POST /ledger/models, GET /ledger/models/{name}/{version}
// (TRD 8.2). The gateway never decides who may register a model: the chaincode refuses a caller
// without role=model-admin, and the gateway only maps that refusal to 403 FORBIDDEN (IF-09).

const AGENT_TOKEN = "a".repeat(32);
const ADMIN_TOKEN = "b".repeat(32);
const VERIFIER_TOKEN = "c".repeat(32);
const UNKNOWN_TOKEN = "z".repeat(32);

const CASE_ID = "CASE-11111111-1111-4111-8111-111111111111";
const EMPTY_CASE_ID = "CASE-22222222-2222-4222-8222-222222222222";
const UNREACHABLE_CASE_ID = "CASE-33333333-3333-4333-8333-333333333333";

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

function modelBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { name: "ecg-cnn", version: "1.0.0", sha256: SHA256, framework: "pytorch", ...overrides };
}

function sevenArtifacts(): Record<string, unknown>[] {
  return PIPELINE.map((artifactType, rank) => ({
    docType: "artifact",
    artifactId: `00000000-0000-4000-8000-00000000000${String(rank)}`,
    caseId: CASE_ID,
    artifactType,
    parentArtifactId:
      rank === 0 ? null : `00000000-0000-4000-8000-00000000000${String(rank - 1)}`,
    creatorAgent: "ingestion",
  }));
}

interface Registration {
  identity: string;
  payload: string;
}

class FakeSession implements LedgerSession {
  readonly histories: { identity: string; caseId: string }[] = [];
  readonly registrations: Registration[] = [];
  readonly lookups: { identity: string; name: string; version: string }[] = [];
  private readonly models = new Map<string, string>();
  failure: Error | undefined;

  create(): Promise<string> {
    return Promise.reject(new Error("create is not used by these routes"));
  }

  read(): Promise<string> {
    return Promise.reject(new Error("read is not used by these routes"));
  }

  history(identity: string, caseId: string): Promise<string> {
    this.histories.push({ identity, caseId });
    if (this.failure !== undefined) {
      return Promise.reject(this.failure);
    }
    if (caseId === UNREACHABLE_CASE_ID) {
      return Promise.reject(new Error("connect ECONNREFUSED 127.0.0.1:7051"));
    }
    return Promise.resolve(caseId === CASE_ID ? JSON.stringify(sevenArtifacts()) : "[]");
  }

  registerModel(identity: string, payload: string): Promise<string> {
    this.registrations.push({ identity, payload });
    if (this.failure !== undefined) {
      return Promise.reject(this.failure);
    }
    // What the chaincode does: the role first, then the duplicate, then the write.
    if (identity !== "model-admin") {
      return Promise.reject(submitRefusal("FORBIDDEN", "RegisterModel requires role model-admin"));
    }
    const client = JSON.parse(payload) as { name: string; version: string };
    const key = `${client.name}@${client.version}`;
    if (this.models.has(key)) {
      return Promise.reject(submitRefusal("DUPLICATE", "model name and version already exist"));
    }
    const stored = JSON.stringify({
      docType: "model",
      ...client,
      registeredAt: "2026-11-15T10:00:00.000Z",
      registeredBy: "x509::CN=model-admin",
    });
    this.models.set(key, stored);
    return Promise.resolve(stored);
  }

  getModel(identity: string, name: string, version: string): Promise<string> {
    this.lookups.push({ identity, name, version });
    if (this.failure !== undefined) {
      return Promise.reject(this.failure);
    }
    if (name === "unreachable") {
      return Promise.reject(new Error("connect ECONNREFUSED 127.0.0.1:7051"));
    }
    const stored = this.models.get(`${name}@${version}`);
    if (stored === undefined) {
      return Promise.reject(evaluateRefusal("NOT_FOUND", "model is not on the ledger"));
    }
    return Promise.resolve(stored);
  }

  close(): void {
    return undefined;
  }
}

describe("history and model routes", () => {
  let app: FastifyInstance;
  let ledger: FakeSession;
  let failures: FailureReport[];
  let base: string;

  beforeEach(async () => {
    ledger = new FakeSession();
    failures = [];
    app = buildApp({
      tokens: TokenDirectory.fromPairs([
        [AGENT_TOKEN, "agent-ingestion"],
        [ADMIN_TOKEN, "model-admin"],
        [VERIFIER_TOKEN, "verifier"],
      ]),
      ledger,
      onFailure: (report) => {
        failures.push(report);
      },
    });
    base = await app.listen({ host: "127.0.0.1", port: 0 });
  });

  afterEach(async () => {
    await app.close();
  });

  describe("authentication comes first, on all three routes", () => {
    const routes = [
      ["GET", `/ledger/cases/${CASE_ID}`, undefined],
      ["POST", "/ledger/models", modelBody()],
      ["GET", "/ledger/models/ecg-cnn/1.0.0", undefined],
    ] as const;

    test.each(routes)("%s %s without a token answers 401", async (method, url, payload) => {
      const response = await call(base, method, url, undefined, payload);

      expect(response.status).toBe(401);
      expect(codeOf(response.body)).toBe("UNAUTHORIZED");
    });

    test.each(routes)("%s %s with an unknown token answers 401 and echoes nothing", async (method, url, payload) => {
      const response = await call(base, method, url, UNKNOWN_TOKEN, payload);

      expect(response.status).toBe(401);
      expect(codeOf(response.body)).toBe("UNAUTHORIZED");
      expect(JSON.stringify(response.body)).not.toContain(UNKNOWN_TOKEN);
      expect(ledger.histories).toEqual([]);
      expect(ledger.registrations).toEqual([]);
      expect(ledger.lookups).toEqual([]);
    });

    test("an unknown token is refused before the request is looked at", async () => {
      const malformedCase = await call(base, "GET", "/ledger/cases/not-a-case", UNKNOWN_TOKEN);
      const malformedModel = await call(base, "GET", "/ledger/models/Bad/latest", UNKNOWN_TOKEN);
      const malformedBody = await callRaw(
        base,
        "/ledger/models",
        { "content-type": "application/json", "X-Agent-Token": UNKNOWN_TOKEN },
        "{",
      );

      expect(malformedCase.status).toBe(401);
      expect(malformedModel.status).toBe(401);
      expect(malformedBody.status).toBe(401);
    });
  });

  describe("GET /ledger/cases/{caseId}", () => {
    test("returns the seven artifacts of a case, parent to child, as the chaincode ordered them", async () => {
      const response = await call(base, "GET", `/ledger/cases/${CASE_ID}`, AGENT_TOKEN);
      const records = response.body as { artifactType: string; parentArtifactId: string | null }[];

      expect(response.status).toBe(200);
      expect(Array.isArray(records)).toBe(true);
      expect(records).toHaveLength(7);
      expect(records.map((record) => record.artifactType)).toEqual([...PIPELINE]);
      expect(records[0]?.parentArtifactId).toBeNull();
      expect(records[6]?.parentArtifactId).toBe("00000000-0000-4000-8000-000000000005");
    });

    // Three tokens, not one: a route that always read as the verifier would pass with one (AUD-100).
    test.each([
      ["an agent of the pipeline", AGENT_TOKEN, "agent-ingestion"],
      ["the model administrator", ADMIN_TOKEN, "model-admin"],
      ["the verifier", VERIFIER_TOKEN, "verifier"],
    ])("reads as %s, with the identity selected by the token", async (_who, token, identity) => {
      await call(base, "GET", `/ledger/cases/${CASE_ID}`, token);

      expect(ledger.histories).toEqual([{ identity, caseId: CASE_ID }]);
    });

    test("a case with no artifact is an empty list, not a 404", async () => {
      const response = await call(base, "GET", `/ledger/cases/${EMPTY_CASE_ID}`, AGENT_TOKEN);

      expect(response.status).toBe(200);
      expect(response.body).toEqual([]);
    });

    test.each([
      ["a case id without the prefix", "11111111-1111-4111-8111-111111111111"],
      ["a short case id", "CASE-1"],
      ["an uppercase case id", "CASE-AAAAAAAA-1111-4111-8111-111111111111"],
      ["a case id with a trailing character", `${CASE_ID}x`],
      ["an encoded slash", "CASE-1%2F..%2Fmodels"],
      ["an encoded null byte", `${CASE_ID.slice(0, 20)}%00${CASE_ID.slice(21)}`],
    ])("refuses %s with 400 SCHEMA and never reaches the ledger", async (_label, caseId) => {
      const response = await call(base, "GET", `/ledger/cases/${caseId}`, AGENT_TOKEN);

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.histories).toEqual([]);
    });

    test("a chaincode refusal keeps its status and text", async () => {
      ledger.failure = evaluateRefusal("SCHEMA", "caseId is not a valid case identifier");
      const response = await call(base, "GET", `/ledger/cases/${CASE_ID}`, AGENT_TOKEN);

      expect(response.status).toBe(400);
      expect(isErrorEnvelope(response.body) ? response.body.error.message : "").toBe(
        "caseId is not a valid case identifier",
      );
      expect(failures).toEqual([]);
    });

    test("an unreachable peer is a 502 UNAVAILABLE, reported with its cause and not the token", async () => {
      const response = await call(base, "GET", `/ledger/cases/${UNREACHABLE_CASE_ID}`, AGENT_TOKEN);

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
      expect(JSON.stringify(response.body)).not.toContain("127.0.0.1");
      expect(failures).toHaveLength(1);
      expect(failures[0]).toMatchObject({ operation: "GetCaseHistory", status: 502 });
      expect(failures[0]?.cause).toContain("ECONNREFUSED");
      expect(JSON.stringify(failures)).not.toContain(AGENT_TOKEN);
    });
  });

  describe("POST /ledger/models", () => {
    test("the model administrator registers a model", async () => {
      const response = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());
      const stored = response.body as Record<string, unknown>;

      expect(response.status).toBe(200);
      expect(stored).toMatchObject({
        docType: "model",
        name: "ecg-cnn",
        version: "1.0.0",
        sha256: SHA256,
        framework: "pytorch",
      });
      expect(typeof stored.registeredAt).toBe("string");
      expect(String(stored.registeredBy)).toContain("CN=model-admin");
      expect(ledger.registrations.map((entry) => entry.identity)).toEqual(["model-admin"]);
    });

    test("passes the body to the ledger as the client sent it", async () => {
      const sent = modelBody({ name: "ecg-cnn-b", version: "2.10.3", framework: "onnx" });
      await call(base, "POST", "/ledger/models", ADMIN_TOKEN, sent);

      expect(JSON.parse(ledger.registrations[0]?.payload ?? "null")).toEqual(sent);
    });

    test("an identity without role=model-admin is refused with 403 FORBIDDEN (IF-09)", async () => {
      const response = await call(base, "POST", "/ledger/models", AGENT_TOKEN, modelBody());

      expect(response.status).toBe(403);
      expect(isErrorEnvelope(response.body)).toBe(true);
      expect(response.body).toEqual({
        error: {
          code: "FORBIDDEN",
          message: "RegisterModel requires role model-admin",
          details: {},
        },
      });
      expect(JSON.stringify(response.body)).not.toContain(AGENT_TOKEN);
      expect(JSON.stringify(response.body)).not.toContain(SHA256);
      // The decision is the chaincode's: the gateway forwards the call under the caller's own
      // identity and does not decide who may register.
      expect(ledger.registrations.map((entry) => entry.identity)).toEqual(["agent-ingestion"]);
      // A refusal the caller caused is not an operator alert.
      expect(failures).toEqual([]);
    });

    test("an identity of the other organization is refused the same way", async () => {
      const response = await call(base, "POST", "/ledger/models", VERIFIER_TOKEN, modelBody());

      expect(response.status).toBe(403);
      expect(codeOf(response.body)).toBe("FORBIDDEN");
    });

    test("a refused registration stores nothing", async () => {
      await call(base, "POST", "/ledger/models", AGENT_TOKEN, modelBody());
      const read = await call(base, "GET", "/ledger/models/ecg-cnn/1.0.0", ADMIN_TOKEN);

      expect(read.status).toBe(404);
    });

    test("a second registration of the same name and version answers 409 DUPLICATE", async () => {
      await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());
      const response = await call(
        base,
        "POST",
        "/ledger/models",
        ADMIN_TOKEN,
        modelBody({ sha256: "cd".repeat(32) }),
      );

      expect(response.status).toBe(409);
      expect(codeOf(response.body)).toBe("DUPLICATE");
      expect(failures).toEqual([]);
    });

    test("another version of the same name is accepted", async () => {
      await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());
      const response = await call(
        base,
        "POST",
        "/ledger/models",
        ADMIN_TOKEN,
        modelBody({ version: "1.0.1" }),
      );

      expect(response.status).toBe(200);
    });

    test.each([
      ["registeredAt", "2026-11-15T10:00:00.000Z"],
      ["registeredBy", "x509::CN=someone-else"],
      ["docType", "model"],
      ["file_path", "models/ecg.pt"],
      ["is_active", true],
      ["patientName", "hidden"],
    ])("never takes %s from the client (closed schema, NFR-03)", async (field, value) => {
      const response = await call(
        base,
        "POST",
        "/ledger/models",
        ADMIN_TOKEN,
        modelBody({ [field]: value }),
      );

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(JSON.stringify(response.body)).not.toContain(String(value));
      expect(ledger.registrations).toEqual([]);
    });

    test.each(["name", "version", "sha256", "framework"])("refuses a body without %s", async (field) => {
      const body = modelBody();
      delete body[field];
      const response = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, body);

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.registrations).toEqual([]);
    });

    const invalid: [string, string, unknown][] = [
      ["an uppercase name", "name", "ECG-CNN"],
      ["a name with a space", "name", "ecg cnn"],
      ["a name with a slash", "name", "ecg/cnn"],
      ["an empty name", "name", ""],
      ["a name over 60 characters", "name", "m".repeat(61)],
      ["a number for name", "name", 7],
      ["null for name", "name", null],
      ["a two-part version", "version", "1.0"],
      ["a version with a prefix", "version", "v1.0.0"],
      ["a version with a suffix", "version", "1.0.0-rc1"],
      ["the word latest", "version", "latest"],
      ["a number for version", "version", 1],
      ["an uppercase sha256", "sha256", "AB".repeat(32)],
      ["a short sha256", "sha256", "ab".repeat(31)],
      ["an array for sha256", "sha256", [SHA256]],
      ["an empty framework", "framework", ""],
      ["a framework over 40 characters", "framework", "f".repeat(41)],
      ["a number for framework", "framework", 7],
      ["null for framework", "framework", null],
    ];

    test.each(invalid)("refuses %s with 400 SCHEMA and never reaches the ledger", async (_label, field, value) => {
      const response = await call(
        base,
        "POST",
        "/ledger/models",
        ADMIN_TOKEN,
        modelBody({ [field]: value }),
      );

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.registrations).toEqual([]);
    });

    test.each([
      ["a name of 60 characters", { name: "m".repeat(60) }],
      ["a name with underscore and hyphen", { name: "ecg_cnn-2" }],
      ["a version of several digits", { version: "10.200.3000" }],
      ["a framework of 1 character", { framework: "f" }],
      ["a framework of 40 characters", { framework: "f".repeat(40) }],
    ])("accepts %s", async (_label, overrides) => {
      const response = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody(overrides));

      expect(response.status).toBe(200);
    });

    test("refuses a body that is not a JSON object", async () => {
      const headers = { "content-type": "application/json", "X-Agent-Token": ADMIN_TOKEN };
      for (const text of ["[]", "null", "7", '"text"', "{", ""]) {
        const response = await callRaw(base, "/ledger/models", headers, text);
        expect(response.status).toBe(400);
        expect(codeOf(response.body)).toBe("SCHEMA");
      }
      expect(ledger.registrations).toEqual([]);
    });

    test("refuses a body that is not declared as JSON", async () => {
      const response = await callRaw(
        base,
        "/ledger/models",
        { "content-type": "text/plain", "X-Agent-Token": ADMIN_TOKEN },
        JSON.stringify(modelBody()),
      );

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.registrations).toEqual([]);
    });

    test("refuses a body over the size limit", async () => {
      const response = await call(
        base,
        "POST",
        "/ledger/models",
        ADMIN_TOKEN,
        modelBody({ framework: "f".repeat(20_000) }),
      );

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.registrations).toEqual([]);
    });

    test("a chaincode SCHEMA refusal keeps its status and text", async () => {
      ledger.failure = submitRefusal("SCHEMA", "framework must contain 1 to 40 characters");
      const response = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());

      expect(response.status).toBe(400);
      expect(isErrorEnvelope(response.body) ? response.body.error.message : "").toBe(
        "framework must contain 1 to 40 characters",
      );
    });

    test("an unreachable peer is a 502, reported with its cause and never the body", async () => {
      ledger.failure = Object.assign(new Error("11 ABORTED: transaction failed (MVCC_READ_CONFLICT)"), {
        name: "CommitError",
        code: 11,
      });
      const response = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
      expect(failures).toHaveLength(1);
      expect(failures[0]).toMatchObject({ operation: "RegisterModel", status: 502 });
      expect(failures[0]?.cause).toContain("MVCC_READ_CONFLICT");
      expect(JSON.stringify(failures)).not.toContain(SHA256);
      expect(JSON.stringify(failures)).not.toContain(ADMIN_TOKEN);
    });
  });

  describe("GET /ledger/models/{name}/{version}", () => {
    test("returns the stored model, for the administrator and for any other identity", async () => {
      const registered = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());
      const asAdmin = await call(base, "GET", "/ledger/models/ecg-cnn/1.0.0", ADMIN_TOKEN);
      const asVerifier = await call(base, "GET", "/ledger/models/ecg-cnn/1.0.0", VERIFIER_TOKEN);
      const asAgent = await call(base, "GET", "/ledger/models/ecg-cnn/1.0.0", AGENT_TOKEN);

      for (const response of [asAdmin, asVerifier, asAgent]) {
        expect(response.status).toBe(200);
        expect(response.body).toEqual(registered.body);
      }
      expect(ledger.lookups).toEqual([
        { identity: "model-admin", name: "ecg-cnn", version: "1.0.0" },
        { identity: "verifier", name: "ecg-cnn", version: "1.0.0" },
        { identity: "agent-ingestion", name: "ecg-cnn", version: "1.0.0" },
      ]);
    });

    test("a model that was never registered is 404 NOT_FOUND in the normalized shape", async () => {
      const response = await call(base, "GET", "/ledger/models/ecg-cnn/9.9.9", AGENT_TOKEN);

      expect(response.status).toBe(404);
      expect(response.body).toEqual({
        error: { code: "NOT_FOUND", message: "model is not on the ledger", details: {} },
      });
      expect(failures).toEqual([]);
    });

    test("another version of a registered name is 404", async () => {
      await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());
      const response = await call(base, "GET", "/ledger/models/ecg-cnn/1.0.1", AGENT_TOKEN);

      expect(response.status).toBe(404);
      expect(codeOf(response.body)).toBe("NOT_FOUND");
    });

    test.each([
      ["an uppercase name", "ECG-CNN", "1.0.0"],
      ["a name over 60 characters", "m".repeat(61), "1.0.0"],
      ["an encoded slash in the name", "ecg%2Fcnn", "1.0.0"],
      ["an encoded null byte in the name", "ecg%00cnn", "1.0.0"],
      ["the word latest", "ecg-cnn", "latest"],
      ["a two-part version", "ecg-cnn", "1.0"],
      ["an encoded space in the version", "ecg-cnn", "1.0.0%20"],
    ])("refuses %s with 400 SCHEMA and never reaches the ledger", async (_label, name, version) => {
      const response = await call(base, "GET", `/ledger/models/${name}/${version}`, AGENT_TOKEN);

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.lookups).toEqual([]);
    });

    test("an unreachable peer is a 502 UNAVAILABLE, reported as GetModel", async () => {
      const response = await call(base, "GET", "/ledger/models/unreachable/1.0.0", AGENT_TOKEN);

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
      expect(failures).toHaveLength(1);
      expect(failures[0]).toMatchObject({ operation: "GetModel", status: 502 });
      expect(JSON.stringify(failures)).not.toContain(AGENT_TOKEN);
    });
  });

  // The router refuses these before any route runs; Fastify's own bodies are not the IF-09
  // envelope (AUD-099). The answer does not depend on the token: no route was matched.
  describe("a URL the router cannot use is answered in the same envelope", () => {
    test.each([
      ["a bad percent-encoding in a case id", "/ledger/cases/%zz"],
      ["a lone percent sign in a case id", "/ledger/cases/CASE-%"],
      ["a bad percent-encoding in a model name", "/ledger/models/%zz/1.0.0"],
      ["a bad percent-encoding in a model version", "/ledger/models/ecg-cnn/%zz"],
      ["a bad percent-encoding in an artifact id", "/ledger/artifacts/%"],
      ["a case id over 100 characters", `/ledger/cases/CASE-${"a".repeat(101)}`],
      ["a model name over 100 characters", `/ledger/models/${"m".repeat(101)}/1.0.0`],
      ["a model version over 100 characters", `/ledger/models/ecg-cnn/${"1".repeat(101)}`],
      ["an artifact id over 100 characters", `/ledger/artifacts/${"a".repeat(101)}`],
    ])("%s answers 400 SCHEMA and never reaches the ledger", async (_label, url) => {
      for (const token of [AGENT_TOKEN, undefined]) {
        const response = await call(base, "GET", url, token);

        expect(response.status).toBe(400);
        expect(response.body).toEqual({
          error: { code: "SCHEMA", message: "requête invalide", details: {} },
        });
      }
      expect(ledger.histories).toEqual([]);
      expect(ledger.lookups).toEqual([]);
    });
  });

  describe("every refusal of these routes has the same envelope (IF-09)", () => {
    test.each([
      ["FORBIDDEN", 403],
      ["NOT_FOUND", 404],
      ["DUPLICATE", 409],
      ["SCHEMA", 400],
    ] as const)("%s answers %i with code, message and empty details", async (code, status) => {
      ledger.failure = submitRefusal(code, "the chaincode's words");
      const response = await call(base, "POST", "/ledger/models", ADMIN_TOKEN, modelBody());

      expect(response.status).toBe(status);
      expect(response.body).toEqual({
        error: { code, message: "the chaincode's words", details: {} },
      });
    });
  });
});
