import { Provenance } from "../src/provenance";
import { context, PIPELINE_AGENT } from "./memory-ledger";

const id = "11111111-1111-4111-8111-111111111111";
const body = {artifactId: id, caseId: `CASE-${id}`, artifactType: "original", sha256: "b".repeat(64), createdAt: "2026-11-24T12:00:00Z", softwareVersion: "0.1.0", modelVersion: null, parentArtifactId: null, offchainRef: `artifact://${id}`};
test("receipt reads the creation transaction without changing the closed record", async () => {
  const {ctx, stub} = context(PIPELINE_AGENT);
  const contract = new Provenance();
  const created = await contract.CreateArtifactRecord(ctx, JSON.stringify(body));
  expect(JSON.parse(await contract.GetArtifactReceipt(ctx, id))).toEqual({txId: "a".repeat(64), sha256: body.sha256});
  expect(await contract.GetArtifactRecord(ctx, id)).toBe(created);
});
test("missing and malformed artifact identifiers are refused", async () => {
  const {ctx, stub} = context(PIPELINE_AGENT); const contract = new Provenance();
  await expect(contract.GetArtifactReceipt(ctx, id)).rejects.toThrow("NOT_FOUND");
  await expect(contract.GetArtifactReceipt(ctx, "../x")).rejects.toThrow("SCHEMA");
});
test("missing or mismatched history is an integrity error", async () => {
  const {ctx, stub} = context(PIPELINE_AGENT); const contract = new Provenance();
  await contract.CreateArtifactRecord(ctx, JSON.stringify(body));
  stub.history.delete(id);
  await expect(contract.GetArtifactReceipt(ctx, id)).rejects.toThrow("INTEGRITY");
  stub.history.set(id, [{txId: "a".repeat(64), isDelete: false, value: Buffer.from(JSON.stringify({...JSON.parse(await contract.GetArtifactRecord(ctx, id)), sha256: "c".repeat(64)}))}]);
  await expect(contract.GetArtifactReceipt(ctx, id)).rejects.toThrow("INTEGRITY");
});
