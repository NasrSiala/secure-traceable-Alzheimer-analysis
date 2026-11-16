import type { FastifyInstance } from "fastify";

import { buildApp } from "../src/app";
import { type FailureReport, isErrorEnvelope } from "../src/errors";
import type { LedgerSession } from "../src/fabric-client";
import { TokenDirectory } from "../src/tokens";
import { call, callRaw, codeOf, evaluateRefusal, submitRefusal } from "./ledger-fixtures";

const TOKEN = "a".repeat(32);
const UNKNOWN = "z".repeat(32);
const ARTIFACT_ID = "11111111-1111-4111-8111-111111111111";
const MISSING_ID = "00000000-0000-4000-8000-000000000099";
const UNREACHABLE_ID = "22222222-2222-4222-8222-222222222222";

function artifactBody(id: string): Record<string, unknown> {
  return {
    artifactId: id,
    caseId: `CASE-${id}`,
    artifactType: "original",
    sha256: "ab".repeat(32),
    createdAt: "2026-11-09T12:00:00.000Z",
    softwareVersion: "0.1.0",
    modelVersion: null,
    parentArtifactId: null,
    offchainRef: `artifact://${id}`,
  };
}

// The artifact routes never reach history or the model registry: the three methods fail the test
// that calls them by mistake (the routes of l08 are tested in ledger-routes.test.ts).
class FakeLedger implements LedgerSession {
  readonly creates: string[] = [];
  readonly payloads: string[] = [];
  failure: Error | undefined;

  async create(identity: string, payload: string): Promise<string> {
    this.creates.push(identity);
    this.payloads.push(payload);
    if (this.failure !== undefined) {
      throw this.failure;
    }
    const body = JSON.parse(payload) as { artifactId?: string };
    if (body.artifactId === ARTIFACT_ID && this.creates.length > 1) {
      throw submitRefusal("DUPLICATE", "artifactId already exists");
    }
    return JSON.stringify({
      docType: "artifact",
      artifactId: body.artifactId,
      creatorAgent: "ingestion",
    });
  }

  async read(identity: string, artifactId: string): Promise<string> {
    if (identity !== "agent-ingestion") {
      throw new Error("unexpected identity");
    }
    if (this.failure !== undefined) {
      throw this.failure;
    }
    if (artifactId === MISSING_ID) {
      throw evaluateRefusal("NOT_FOUND", "artifactId is not on the ledger");
    }
    if (artifactId === UNREACHABLE_ID) {
      throw new Error("connect ECONNREFUSED 127.0.0.1:7051");
    }
    return JSON.stringify({ docType: "artifact", artifactId, creatorAgent: "ingestion" });
  }

  history(): Promise<string> {
    return Promise.reject(new Error("history is not used by the artifact routes"));
  }

  registerModel(): Promise<string> {
    return Promise.reject(new Error("registerModel is not used by the artifact routes"));
  }

  getModel(): Promise<string> {
    return Promise.reject(new Error("getModel is not used by the artifact routes"));
  }

  close(): void {
    return undefined;
  }
}

describe("artifact routes", () => {
  let app: FastifyInstance;
  let ledger: FakeLedger;
  let failures: FailureReport[];
  let base: string;

  beforeEach(async () => {
    ledger = new FakeLedger();
    failures = [];
    app = buildApp({
      tokens: TokenDirectory.fromPairs([[TOKEN, "agent-ingestion"]]),
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

  test("rejects an unknown token with 401 and the error envelope", async () => {
    const response = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, UNKNOWN);

    expect(response.status).toBe(401);
    expect(isErrorEnvelope(response.body)).toBe(true);
    expect(isErrorEnvelope(response.body) ? response.body.error.code : "").toBe("UNAUTHORIZED");
    expect(JSON.stringify(response.body)).not.toContain(UNKNOWN);
    expect(ledger.creates).toEqual([]);
  });

  test("rejects a missing token with 401", async () => {
    const response = await call(base, "POST", "/ledger/artifacts", undefined, artifactBody(ARTIFACT_ID));

    expect(response.status).toBe(401);
    expect(isErrorEnvelope(response.body)).toBe(true);
  });

  test("takes the token from X-Agent-Token only", async () => {
    const response = await fetch(`${base}/ledger/artifacts/${ARTIFACT_ID}`, {
      headers: { Authorization: `Bearer ${TOKEN}` },
    });

    expect(response.status).toBe(401);
  });

  test("checks the token before it looks at the request", async () => {
    const malformedId = await call(base, "GET", "/ledger/artifacts/not-a-uuid", UNKNOWN);
    const malformedBody = await callRaw(
      base,
      "/ledger/artifacts",
      { "content-type": "application/json", "X-Agent-Token": UNKNOWN },
      "{",
    );

    expect(malformedId.status).toBe(401);
    expect(malformedBody.status).toBe(401);
  });

  test("creates and reads with the identity selected by the token", async () => {
    const created = await call(
      base,
      "POST",
      "/ledger/artifacts",
      TOKEN,
      artifactBody(ARTIFACT_ID),
    );
    const read = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);
    const createdBody = created.body as { artifactId?: string; creatorAgent?: string };
    const readBody = read.body as { artifactId?: string };

    expect(created.status).toBe(200);
    expect(createdBody.artifactId).toBe(ARTIFACT_ID);
    expect(createdBody.creatorAgent).toBe("ingestion");
    expect(read.status).toBe(200);
    expect(readBody.artifactId).toBe(ARTIFACT_ID);
    expect(ledger.creates).toEqual(["agent-ingestion"]);
  });

  test("passes the body to the ledger as the client sent it", async () => {
    const sent = artifactBody(ARTIFACT_ID);
    await call(base, "POST", "/ledger/artifacts", TOKEN, sent);

    expect(JSON.parse(ledger.payloads[0] ?? "null")).toEqual(sent);
  });

  test("accepts a model version and a parent", async () => {
    const parent = "33333333-3333-4333-8333-333333333333";
    const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
      ...artifactBody("44444444-4444-4444-8444-444444444444"),
      artifactType: "prediction",
      modelVersion: "ecg-cnn-1.0.0",
      parentArtifactId: parent,
    });

    expect(response.status).toBe(200);
    const sent = JSON.parse(ledger.payloads[0] ?? "{}") as Record<string, unknown>;
    expect(sent.modelVersion).toBe("ecg-cnn-1.0.0");
    expect(sent.parentArtifactId).toBe(parent);
  });

  test("accepts a body without modelVersion", async () => {
    const body = artifactBody(ARTIFACT_ID);
    delete body.modelVersion;
    const response = await call(base, "POST", "/ledger/artifacts", TOKEN, body);

    expect(response.status).toBe(200);
    expect(JSON.parse(ledger.payloads[0] ?? "{}")).not.toHaveProperty("modelVersion");
  });

  test("returns 409 DUPLICATE with the normalized envelope", async () => {
    await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));
    const response = await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));

    expect(response.status).toBe(409);
    expect(isErrorEnvelope(response.body) ? response.body.error.code : "").toBe("DUPLICATE");
    expect(isErrorEnvelope(response.body) ? response.body.error.details : undefined).toEqual({});
  });

  test("returns 404 when the record is absent", async () => {
    const response = await call(base, "GET", `/ledger/artifacts/${MISSING_ID}`, TOKEN);

    expect(response.status).toBe(404);
    expect(isErrorEnvelope(response.body) ? response.body.error.code : "").toBe("NOT_FOUND");
  });

  test("returns 502 when the peer cannot be reached", async () => {
    const response = await call(
      base,
      "GET",
      "/ledger/artifacts/22222222-2222-4222-8222-222222222222",
      TOKEN,
    );

    expect(response.status).toBe(502);
    expect(isErrorEnvelope(response.body) ? response.body.error.code : "").toBe("UNAVAILABLE");
    expect(JSON.stringify(response.body)).not.toContain("127.0.0.1");
  });

  test.each([
    ["creatorMspId", "Org9MSP"],
    ["creatorId", "x509::/CN=someone-else"],
    ["creatorAgent", "validation"],
    ["txTimestamp", "2026-11-09T18:00:00.000Z"],
    ["docType", "artifact"],
  ])("never takes %s from the client (NFR-06)", async (field, value) => {
    const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
      ...artifactBody(ARTIFACT_ID),
      [field]: value,
    });

    expect(response.status).toBe(400);
    expect(codeOf(response.body)).toBe("SCHEMA");
    expect(JSON.stringify(response.body)).not.toContain(value);
    expect(ledger.creates).toEqual([]);
  });

  test("rejects an unknown field before calling the ledger", async () => {
    const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
      ...artifactBody(ARTIFACT_ID),
      patientName: "hidden",
    });

    expect(response.status).toBe(400);
    expect(isErrorEnvelope(response.body) ? response.body.error.code : "").toBe("SCHEMA");
    expect(JSON.stringify(response.body)).not.toContain("patientName");
    expect(JSON.stringify(response.body)).not.toContain("hidden");
    expect(ledger.creates).toEqual([]);
  });

  describe("a closed schema refuses what does not fit; it never repairs it (AUD-069)", () => {
    const cases: [string, string, unknown][] = [
      ["a number for softwareVersion", "softwareVersion", 123],
      ["an array for softwareVersion", "softwareVersion", ["0.1.0"]],
      ["an empty modelVersion", "modelVersion", ""],
      ["zero for modelVersion", "modelVersion", 0],
      ["false for modelVersion", "modelVersion", false],
      ["an empty parentArtifactId", "parentArtifactId", ""],
      ["an array for sha256", "sha256", ["ab".repeat(32)]],
      ["a number for createdAt", "createdAt", 20261109],
      ["a number for caseId", "caseId", 7],
      ["null for artifactType", "artifactType", null],
    ];

    test.each(cases)("%s answers 400 and never reaches the ledger", async (_label, field, value) => {
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
        ...artifactBody(ARTIFACT_ID),
        [field]: value,
      });

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.creates).toEqual([]);
    });
  });

  describe("validation", () => {
    const invalid: [string, string, unknown][] = [
      ["an uppercase sha256", "sha256", "AB".repeat(32)],
      ["a short sha256", "sha256", "ab".repeat(31)],
      ["an artifactType outside the list", "artifactType", "diagnosis"],
      ["a malformed artifactId", "artifactId", "not-a-uuid"],
      ["an uppercase artifactId", "artifactId", "AAAAAAAA-1111-4111-8111-111111111111"],
      ["a malformed caseId", "caseId", "CASE-1"],
      ["a malformed parentArtifactId", "parentArtifactId", "parent"],
      ["an empty softwareVersion", "softwareVersion", ""],
      ["a softwareVersion over 64 characters", "softwareVersion", "v".repeat(65)],
      ["a modelVersion over 64 characters", "modelVersion", "m".repeat(65)],
      ["an offchainRef over 80 characters", "offchainRef", `artifact://${"x".repeat(80)}`],
    ];

    test.each(invalid)("refuses %s with 400 SCHEMA", async (_label, field, value) => {
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
        ...artifactBody(ARTIFACT_ID),
        [field]: value,
      });

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.creates).toEqual([]);
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
    ])("refuses a body without %s", async (field) => {
      const body = artifactBody(ARTIFACT_ID);
      delete body[field];
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, body);

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.creates).toEqual([]);
    });

    test("refuses an offchainRef that does not name the artifact", async () => {
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
        ...artifactBody(ARTIFACT_ID),
        offchainRef: `artifact://${MISSING_ID}`,
      });

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.creates).toEqual([]);
    });

    test("refuses a body that is not a JSON object", async () => {
      const headers = { "content-type": "application/json", "X-Agent-Token": TOKEN };
      for (const text of ["[]", "null", "7", '"text"', "{", ""]) {
        const response = await callRaw(base, "/ledger/artifacts", headers, text);
        expect(response.status).toBe(400);
        expect(codeOf(response.body)).toBe("SCHEMA");
      }
      expect(ledger.creates).toEqual([]);
    });

    test("refuses a body over the size limit", async () => {
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, {
        ...artifactBody(ARTIFACT_ID),
        softwareVersion: "v".repeat(20_000),
      });

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.creates).toEqual([]);
    });

    test("refuses a body that is not declared as JSON", async () => {
      const response = await callRaw(
        base,
        "/ledger/artifacts",
        { "content-type": "text/plain", "X-Agent-Token": TOKEN },
        JSON.stringify(artifactBody(ARTIFACT_ID)),
      );

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
      expect(ledger.creates).toEqual([]);
    });

    test("refuses a malformed artifact id on read without calling the ledger", async () => {
      const response = await call(base, "GET", "/ledger/artifacts/not-a-uuid", TOKEN);

      expect(response.status).toBe(400);
      expect(codeOf(response.body)).toBe("SCHEMA");
    });
  });

  describe("chaincode answers keep their meaning (IF-09)", () => {
    const refusals: [string, number, string, (code: string, detail: string) => Error][] = [
      ["SCHEMA", 400, "missing field caseId", submitRefusal],
      ["FORBIDDEN", 403, "CreateArtifactRecord requires role pipeline-agent", submitRefusal],
      ["NOT_FOUND", 404, "artifactId is not on the ledger", submitRefusal],
      ["DUPLICATE", 409, "artifactId already exists", submitRefusal],
      ["PARENT_MISSING", 422, "parent artifact does not exist", submitRefusal],
      ["SCHEMA", 400, "createdAt must be ISO 8601 UTC", evaluateRefusal],
      ["NOT_FOUND", 404, "artifactId is not on the ledger", evaluateRefusal],
    ];

    test.each(refusals)("%s answers %i with the chaincode text", async (code, status, detail, make) => {
      ledger.failure = make(code, detail);
      const created = await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));
      const read = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);

      for (const response of [created, read]) {
        expect(response.status).toBe(status);
        expect(isErrorEnvelope(response.body) ? response.body.error.code : "").toBe(code);
        expect(isErrorEnvelope(response.body) ? response.body.error.message : "").toBe(detail);
      }
      expect(failures).toEqual([]);
    });

    test("a transport status named NOT_FOUND is not an answer about the record (AUD-078)", async () => {
      ledger.failure = new Error("5 NOT_FOUND: channel does not exist");
      const response = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
    });

    test("a chaincode code in the middle of other text is not read as a refusal", async () => {
      ledger.failure = new Error("14 UNAVAILABLE: peer said FORBIDDEN: not a chaincode answer");
      const response = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
    });

    test("a chaincode code that IF-09 does not know is a 502", async () => {
      ledger.failure = submitRefusal("TEAPOT", "short and stout");
      const response = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
    });
  });

  describe("an operator can tell why the ledger failed (AUD-071)", () => {
    test("reports the cause of a 502 without the token or the body", async () => {
      const response = await call(base, "GET", `/ledger/artifacts/${UNREACHABLE_ID}`, TOKEN);

      expect(response.status).toBe(502);
      expect(failures).toHaveLength(1);
      expect(failures[0]).toMatchObject({ operation: "GetArtifactRecord", status: 502 });
      expect(failures[0]?.cause).toContain("ECONNREFUSED");
      expect(JSON.stringify(failures)).not.toContain(TOKEN);
    });

    test("reports a failed create, and never the payload", async () => {
      ledger.failure = Object.assign(new Error("11 ABORTED: transaction failed (MVCC_READ_CONFLICT)"), {
        name: "CommitError",
        code: 11,
      });
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));

      expect(response.status).toBe(502);
      expect(failures).toHaveLength(1);
      expect(failures[0]).toMatchObject({ operation: "CreateArtifactRecord", status: 502 });
      expect(failures[0]?.cause).toContain("CommitError");
      expect(failures[0]?.cause).toContain("code=11");
      expect(failures[0]?.cause).toContain("MVCC_READ_CONFLICT");
      expect(JSON.stringify(failures)).not.toContain("sha256");
      expect(JSON.stringify(failures)).not.toContain(TOKEN);
    });

    test("keeps the cause to one line", async () => {
      ledger.failure = new Error(`first line\nsecond line ${"x".repeat(1000)}`);
      await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);

      expect(failures[0]?.cause).toBe("Error: first line");
    });

    test("a failed submit reports the chaincode's refusal from its details", async () => {
      ledger.failure = submitRefusal("INTEGRITY", "a stored record is not valid JSON");
      const response = await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
      expect(JSON.stringify(response.body)).not.toContain("INTEGRITY");
      expect(failures).toHaveLength(1);
      expect(failures[0]?.cause).toContain("failed to endorse transaction");
      expect(failures[0]?.cause).toContain(
        "chaincode response 500, INTEGRITY: a stored record is not valid JSON",
      );
    });

    test("a failed evaluate reports the chaincode's refusal from its message", async () => {
      ledger.failure = evaluateRefusal("INTEGRITY", "an indexed artifact is not on the ledger");
      const response = await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, TOKEN);

      expect(response.status).toBe(502);
      expect(codeOf(response.body)).toBe("UNAVAILABLE");
      expect(failures[0]?.cause).toContain("INTEGRITY: an indexed artifact is not on the ledger");
    });

    test("names each distinct endorsement detail once", async () => {
      ledger.failure = Object.assign(new Error("10 ABORTED: failed to endorse transaction"), {
        details: [
          { message: "chaincode response 500, INTEGRITY: one\nstack line" },
          { message: "chaincode response 500, INTEGRITY: one\nstack line" },
          { message: "peer unreachable" },
          { message: "" },
        ],
      });
      await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));

      expect(failures[0]?.cause).toBe(
        "Error: 10 ABORTED: failed to endorse transaction | " +
          "chaincode response 500, INTEGRITY: one | peer unreachable",
      );
    });

    test("does not report answers the caller caused", async () => {
      await call(base, "GET", `/ledger/artifacts/${MISSING_ID}`, TOKEN);
      await call(base, "GET", `/ledger/artifacts/${ARTIFACT_ID}`, UNKNOWN);
      await call(base, "GET", "/ledger/artifacts/not-a-uuid", TOKEN);
      await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));
      await call(base, "POST", "/ledger/artifacts", TOKEN, artifactBody(ARTIFACT_ID));

      expect(failures).toEqual([]);
    });

    test("a failing log sink does not change the answer", async () => {
      const quiet = buildApp({
        tokens: TokenDirectory.fromPairs([[TOKEN, "agent-ingestion"]]),
        ledger,
        onFailure: () => {
          throw new Error("disk full");
        },
      });
      const address = await quiet.listen({ host: "127.0.0.1", port: 0 });
      try {
        const response = await call(address, "GET", `/ledger/artifacts/${UNREACHABLE_ID}`, TOKEN);

        expect(response.status).toBe(502);
        expect(codeOf(response.body)).toBe("UNAVAILABLE");
      } finally {
        await quiet.close();
      }
    });
  });

  describe("an unknown route answers in the normalized form (AUD-074)", () => {
    test.each([
      ["GET", "/ledger/nope"],
      ["GET", "/health"],
      ["DELETE", "/ledger/artifacts"],
      // /ledger/cases/{caseId} and /ledger/models are routes since l08; these are not.
      ["GET", "/ledger/cases"],
      ["DELETE", "/ledger/cases/CASE-00000000-0000-4000-8000-000000000001"],
      ["GET", "/ledger/models"],
      ["GET", "/ledger/models/ecg-cnn"],
      ["DELETE", "/ledger/models"],
    ] as const)("%s %s", async (method, url) => {
      const response = await call(base, method, url, TOKEN);

      expect(response.status).toBe(404);
      expect(isErrorEnvelope(response.body)).toBe(true);
      expect(codeOf(response.body)).toBe("NOT_FOUND");
    });
  });
});
