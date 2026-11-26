import { buildApp } from "../src/app";
import { TokenDirectory } from "../src/tokens";

const id = "11111111-1111-4111-8111-111111111111";
const token = "a".repeat(32);
const body = {artifactId: id, caseId: `CASE-${id}`, artifactType: "original", sha256: "b".repeat(64), createdAt: "2026-11-24T12:00:00Z", softwareVersion: "0.1.0", modelVersion: null, parentArtifactId: null, offchainRef: `artifact://${id}`};
test.each(["GET", "POST"] as const)("%s carries a receipt in a header without extending the record", async method => {
  const app = buildApp({tokens: TokenDirectory.fromPairs([[token, "agent-ingestion"]]), ledger: {
    create: async () => JSON.stringify(body), read: async () => JSON.stringify(body),
    receipt: async () => JSON.stringify({txId: "c".repeat(64), sha256: body.sha256}),
    history: async () => "[]", registerModel: async () => "{}", getModel: async () => "{}", close() {},
  }});
  try {
    const address = await app.listen({host: "127.0.0.1", port: 0});
    const response = await fetch(address + (method === "POST" ? "/ledger/artifacts" : `/ledger/artifacts/${id}`), {method, headers: {"X-Agent-Token": token, "content-type": "application/json"}, ...(method === "POST" ? {body: JSON.stringify(body)} : {})});
    expect(response.status).toBe(200);
    expect(response.headers.get("x-fabric-transaction-id")).toBe("c".repeat(64));
    expect((await response.json()) as unknown).toEqual(body);
  } finally { await app.close(); }
});
test.each([{txId: "short", sha256: body.sha256}, {txId: "c".repeat(64), sha256: "d".repeat(64)}])("invalid or mismatched receipts are unavailable", async receipt => {
  const app = buildApp({tokens: TokenDirectory.fromPairs([[token, "agent-ingestion"]]), onFailure: () => undefined, ledger: {
    create: async () => JSON.stringify(body), read: async () => JSON.stringify(body), receipt: async () => JSON.stringify(receipt),
    history: async () => "[]", registerModel: async () => "{}", getModel: async () => "{}", close() {},
  }});
  try {
    const address = await app.listen({host: "127.0.0.1", port: 0});
    const response = await fetch(address + `/ledger/artifacts/${id}`, {headers: {"X-Agent-Token": token}});
    expect(response.status).toBe(502);
    expect(response.headers.get("x-fabric-transaction-id")).toBeNull();
  } finally { await app.close(); }
});
