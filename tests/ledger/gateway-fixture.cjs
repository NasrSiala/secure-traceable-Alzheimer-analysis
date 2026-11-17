// Vraie application Fastify ; seul l'adaptateur Fabric est remplacé en mémoire.
const path = require("node:path");
const { buildApp } = require(path.resolve("ledger-gateway/dist/app.js"));
const { TokenDirectory } = require(path.resolve("ledger-gateway/dist/tokens.js"));
const records = new Map();
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
  close() {},
};
const app = buildApp({ tokens: TokenDirectory.fromPairs([
  [process.env.TEST_AGENT_TOKEN, "agent-ingestion"],
  [process.env.TEST_VERIFIER_TOKEN, "verifier"],
]), ledger });
app.listen({ host: "127.0.0.1", port: 0 }).then(address => {
  process.stdout.write(JSON.stringify({ address }) + "\n");
}).catch(() => process.exit(1));
process.on("SIGTERM", () => app.close().then(() => process.exit(0)));
