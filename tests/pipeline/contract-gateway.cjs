// Real Fastify + Provenance contract; only Fabric's state/certificates are in memory.
const path = require("node:path");
const { randomBytes } = require("node:crypto");
const { Provenance } = require(path.resolve("chaincode/provenance/dist-test/src/provenance.js"));
const { MemoryStub, MemoryIdentity } = require(path.resolve("chaincode/provenance/dist-test/test/memory-ledger.js"));
const { buildApp } = require(path.resolve("ledger-gateway/dist/app.js"));
const { TokenDirectory } = require(path.resolve("ledger-gateway/dist/tokens.js"));

class TransactionStub extends MemoryStub {
  async putState(key, value) {
    await super.putState(key, value);
    this.history.get(key).at(-1).txId = this.txId;
  }
}
const stub = new TransactionStub();
const contract = new Provenance();
function context(identity) {
  return {
    stub,
    clientIdentity: new MemoryIdentity({
      role: identity.startsWith("agent-") ? "pipeline-agent" : null,
      agent: identity.startsWith("agent-") ? identity.slice(6) : null,
      mspId: identity === "verifier" ? "Org2MSP" : "Org1MSP",
      id: `x509::/CN=${identity}/OU=client::/CN=ca.example.com`,
    }),
  };
}
const ledger = {
  async create(identity, payload) {
    stub.txId = randomBytes(32).toString("hex");
    return contract.CreateArtifactRecord(context(identity), payload);
  },
  read: (identity, id) => contract.GetArtifactRecord(context(identity), id),
  receipt: (identity, id) => contract.GetArtifactReceipt(context(identity), id),
  history: (identity, id) => contract.GetCaseHistory(context(identity), id),
  close() {},
};
const tokens = JSON.parse(process.env.TEST_PIPELINE_TOKENS);
const app = buildApp({
  tokens: TokenDirectory.fromPairs(Object.entries(tokens).map(([identity, token]) => [token, identity])),
  ledger,
});
app.listen({ host: "127.0.0.1", port: 0 }).then(address => {
  process.stdout.write(JSON.stringify({ address }) + "\n");
}).catch(() => process.exit(1));
process.on("SIGTERM", () => app.close().then(() => process.exit(0)));
