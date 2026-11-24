// Vraie application Fastify ; seul l'adaptateur Fabric est remplacé en mémoire.
const path = require("node:path");
const { buildApp } = require(path.resolve("ledger-gateway/dist/app.js"));
const { TokenDirectory } = require(path.resolve("ledger-gateway/dist/tokens.js"));
const records = new Map();
const models = new Map();
const ledger = {
  async create(identity, payload) {
    if (identity !== "agent-ingestion") throw new Error("chaincode response 500, FORBIDDEN: role required");
    const record = JSON.parse(payload);
    if (records.has(record.artifactId)) throw new Error("chaincode response 500, DUPLICATE: already exists");
    if (record.parentArtifactId !== null) throw new Error("chaincode response 500, PARENT_MISSING: parent missing");
    const anchored = { ...record, docType: "ARTIFACT", creatorMspId: "Org1MSP", creatorId: "synthetic-agent", txTimestamp: record.createdAt };
    records.set(record.artifactId, anchored);
    return JSON.stringify(anchored);
  },
  async read(_identity, id) {
    if (id === "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee") throw new Error("peer unavailable");
    if (!records.has(id)) throw new Error("chaincode response 500, NOT_FOUND: absent");
    return JSON.stringify(records.get(id));
  },
  async history(_identity, caseId) {
    return JSON.stringify([...records.values()].filter(record => record.caseId === caseId));
  },
  async registerModel(identity, payload) {
    if (identity !== "model-admin") throw new Error("chaincode response 500, FORBIDDEN: model-admin required");
    const model = JSON.parse(payload);
    const key = model.name + ":" + model.version;
    if (models.has(key)) throw new Error("chaincode response 500, DUPLICATE: model exists");
    const anchored = { ...model, docType: "MODEL", registeredBy: "synthetic-model-admin", registeredAt: "2026-11-24T12:00:00Z" };
    models.set(key, anchored);
    return JSON.stringify(anchored);
  },
  async getModel(_identity, name, version) {
    const key = name + ":" + version;
    if (!models.has(key)) throw new Error("chaincode response 500, NOT_FOUND: model absent");
    return JSON.stringify(models.get(key));
  },
  close() {},
};
const app = buildApp({ tokens: TokenDirectory.fromPairs([
  [process.env.TEST_AGENT_TOKEN, "agent-ingestion"],
  [process.env.TEST_VERIFIER_TOKEN, "verifier"],
  [process.env.TEST_AGENT_TOKEN + "-admin", "model-admin"],
]), ledger });
app.listen({ host: "127.0.0.1", port: 0 }).then(address => {
  process.stdout.write(JSON.stringify({ address }) + "\n");
}).catch(() => process.exit(1));
process.on("SIGTERM", () => app.close().then(() => process.exit(0)));
