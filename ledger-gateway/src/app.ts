import Fastify, {
  type FastifyError,
  type FastifyInstance,
  type FastifyReply,
  type FastifyRequest,
} from "fastify";

import { chaincodeFailure, describeCause, errorBody, type FailureReport } from "./errors";
import type { LedgerSession } from "./fabric-client";
import type { TokenDirectory } from "./tokens";

declare module "fastify" {
  interface FastifyRequest {
    agentIdentity?: string;
  }
}

const UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$";

const artifactBody = {
  type: "object",
  additionalProperties: false,
  required: [
    "artifactId",
    "caseId",
    "artifactType",
    "sha256",
    "createdAt",
    "softwareVersion",
    "parentArtifactId",
    "offchainRef",
  ],
  properties: {
    artifactId: { type: "string", pattern: UUID },
    caseId: { type: "string", pattern: "^CASE-[0-9a-f-]{36}$" },
    artifactType: {
      type: "string",
      enum: [
        "original",
        "processed",
        "features",
        "prediction",
        "validation",
        "explanation",
        "final_result",
      ],
    },
    sha256: { type: "string", pattern: "^[0-9a-f]{64}$" },
    createdAt: { type: "string", minLength: 1, maxLength: 40 },
    softwareVersion: { type: "string", minLength: 1, maxLength: 64 },
    modelVersion: {
      anyOf: [{ type: "null" }, { type: "string", minLength: 1, maxLength: 64 }],
    },
    parentArtifactId: {
      anyOf: [{ type: "null" }, { type: "string", pattern: UUID }],
    },
    offchainRef: { type: "string", minLength: 1, maxLength: 80 },
  },
} as const;

const artifactParams = {
  type: "object",
  required: ["id"],
  additionalProperties: false,
  properties: {
    id: { type: "string", pattern: UUID },
  },
} as const;

const caseParams = {
  type: "object",
  required: ["caseId"],
  additionalProperties: false,
  properties: {
    caseId: { type: "string", pattern: "^CASE-[0-9a-f-]{36}$" },
  },
} as const;

// MODEL (Schema 5.2). The chaincode checks the same rules (chaincode/provenance/src/model.ts);
// the gateway refuses early what it would refuse, as it does for ARTIFACT. The two copies are
// compared by tests/scripts/test_model_schema_parity.py.
const MODEL_NAME = "^[a-z0-9_-]{1,60}$";
const MODEL_VERSION = "^[0-9]+\\.[0-9]+\\.[0-9]+$";

const modelBody = {
  type: "object",
  additionalProperties: false,
  required: ["name", "version", "sha256", "framework"],
  properties: {
    name: { type: "string", pattern: MODEL_NAME },
    version: { type: "string", pattern: MODEL_VERSION },
    sha256: { type: "string", pattern: "^[0-9a-f]{64}$" },
    framework: { type: "string", minLength: 1, maxLength: 40 },
  },
} as const;

const modelParams = {
  type: "object",
  required: ["name", "version"],
  additionalProperties: false,
  properties: {
    name: { type: "string", pattern: MODEL_NAME },
    version: { type: "string", pattern: MODEL_VERSION },
  },
} as const;

function presentedToken(request: FastifyRequest): string | undefined {
  const header = request.headers["x-agent-token"];
  if (typeof header !== "string" || header === "") {
    return undefined;
  }
  return header;
}

function requireIdentity(request: FastifyRequest): string {
  const identity = request.agentIdentity;
  if (identity === undefined) {
    throw new Error("missing agent identity");
  }
  return identity;
}

export function buildApp(options: {
  tokens: TokenDirectory;
  ledger: LedgerSession;
  /** Called for every answer with status 500 or above, so the cause is not lost. */
  onFailure?: (report: FailureReport) => void;
}): FastifyInstance {
  // The schema is closed (NFR-03): refuse what does not fit instead of repairing it. Fastify's
  // Ajv defaults coerce types ("123" for 123, null for "" or 0 or false) and apply defaults.
  function requestPath(request: FastifyRequest): string {
    const url = request.raw.url ?? request.url;
    return url.split("?")[0] ?? "";
  }

  function ledgerMissingToken(request: FastifyRequest): boolean {
    const path = requestPath(request);
    if (path !== "/ledger" && !path.startsWith("/ledger/")) {
      return false;
    }
    return options.tokens.identityFor(presentedToken(request)) === null;
  }

  const app = Fastify({
    logger: false,
    bodyLimit: 16 * 1024,
    ajv: {
      customOptions: { coerceTypes: false, useDefaults: false, removeAdditional: false },
    },
    // The router refuses two kinds of URL before any route, hook or error handler runs: a bad
    // percent-encoding and a path parameter over 100 characters. Fastify would answer them in its
    // own shape (400 FST_ERR_BAD_URL, 414 FST_ERR_MAX_PARAM_LENGTH); IF-09 has one body.
    // A /ledger URL still has to present a token before that refusal says anything else.
    frameworkErrors: (_error, request, reply) => {
      // The option types the reply with generics that `.code()` does not accept as a number.
      const answer = reply as FastifyReply;
      if (ledgerMissingToken(request)) {
        void answer.code(401).send(errorBody("UNAUTHORIZED", "jeton absent ou inconnu"));
        return;
      }
      void answer.code(400).send(errorBody("SCHEMA", "requête invalide"));
    },
  });

  function report(operation: string, status: number, error: unknown): void {
    if (status < 500 || options.onFailure === undefined) {
      return;
    }
    try {
      options.onFailure({ operation, status, cause: describeCause(error) });
    } catch {
      // A failing log sink must not change the answer.
    }
  }

  async function sendFailure(
    reply: FastifyReply,
    operation: string,
    error: unknown,
  ): Promise<void> {
    const failure = chaincodeFailure(error);
    report(operation, failure.status, error);
    await reply.code(failure.status).send(failure.body);
  }

  app.setNotFoundHandler((request, reply) => {
    if (ledgerMissingToken(request)) {
      void reply.code(401).send(errorBody("UNAUTHORIZED", "jeton absent ou inconnu"));
      return;
    }
    void reply.code(404).send(errorBody("NOT_FOUND", "route inconnue"));
  });

  app.setErrorHandler((error: FastifyError, request, reply) => {
    const statusCode = error.statusCode ?? 0;
    if (error.validation !== undefined || (statusCode >= 400 && statusCode < 500)) {
      void reply.code(400).send(errorBody("SCHEMA", "requête invalide"));
      return;
    }
    report(`${request.method} ${request.routeOptions.url ?? "unknown"}`, 502, error);
    void reply.code(502).send(errorBody("UNAVAILABLE", "registre injoignable"));
  });

  app.register((routes, _opts, done) => {
    routes.addHook("onRequest", async (request, reply) => {
      const identity = options.tokens.identityFor(presentedToken(request));
      if (identity === null) {
        return reply.code(401).send(errorBody("UNAUTHORIZED", "jeton absent ou inconnu"));
      }
      request.agentIdentity = identity;
      return undefined;
    });

    routes.post("/artifacts", { schema: { body: artifactBody } }, async (request, reply) => {
      const identity = requireIdentity(request);
      const body = request.body as {
        artifactId: string;
        offchainRef: string;
      };
      if (body.offchainRef !== `artifact://${body.artifactId}`) {
        return reply
          .code(400)
          .send(errorBody("SCHEMA", "offchainRef must be artifact:// followed by artifactId"));
      }
      try {
        const raw = await options.ledger.create(identity, JSON.stringify(request.body));
        return reply.code(200).send(JSON.parse(raw) as unknown);
      } catch (error) {
        await sendFailure(reply, "CreateArtifactRecord", error);
        return undefined;
      }
    });

    routes.get("/artifacts/:id", { schema: { params: artifactParams } }, async (request, reply) => {
      const identity = requireIdentity(request);
      const { id } = request.params as { id: string };
      try {
        const raw = await options.ledger.read(identity, id);
        return reply.code(200).send(JSON.parse(raw) as unknown);
      } catch (error) {
        await sendFailure(reply, "GetArtifactRecord", error);
        return undefined;
      }
    });

    // The history of a case, parent to child, as the chaincode ordered it (TRD 8.2).
    routes.get("/cases/:caseId", { schema: { params: caseParams } }, async (request, reply) => {
      const identity = requireIdentity(request);
      const { caseId } = request.params as { caseId: string };
      try {
        const raw = await options.ledger.history(identity, caseId);
        return reply.code(200).send(JSON.parse(raw) as unknown);
      } catch (error) {
        await sendFailure(reply, "GetCaseHistory", error);
        return undefined;
      }
    });

    // Who may register a model is the chaincode's decision (role=model-admin, AC-04.3): the call
    // goes out under the caller's own identity and a refusal comes back as 403 FORBIDDEN.
    routes.post("/models", { schema: { body: modelBody } }, async (request, reply) => {
      const identity = requireIdentity(request);
      try {
        const raw = await options.ledger.registerModel(identity, JSON.stringify(request.body));
        return reply.code(200).send(JSON.parse(raw) as unknown);
      } catch (error) {
        await sendFailure(reply, "RegisterModel", error);
        return undefined;
      }
    });

    routes.get(
      "/models/:name/:version",
      { schema: { params: modelParams } },
      async (request, reply) => {
        const identity = requireIdentity(request);
        const { name, version } = request.params as { name: string; version: string };
        try {
          const raw = await options.ledger.getModel(identity, name, version);
          return reply.code(200).send(JSON.parse(raw) as unknown);
        } catch (error) {
          await sendFailure(reply, "GetModel", error);
          return undefined;
        }
      },
    );

    done();
  }, { prefix: "/ledger" });

  return app;
}
