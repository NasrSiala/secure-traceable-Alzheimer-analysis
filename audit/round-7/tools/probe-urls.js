// Audit probe: how the closed routes answer odd URLs. Run inside the pinned image on a build copy.
const { buildApp } = require("./dist/app");
const { TokenDirectory } = require("./dist/tokens");
const T = "a".repeat(32);
const ledger = {
  create: async () => "{}", read: async () => "{}", history: async () => "[]",
  registerModel: async () => "{}", getModel: async () => "{}", close() {},
};
(async () => {
  const app = buildApp({ tokens: TokenDirectory.fromPairs([[T, "agent-ingestion"]]), ledger });
  const CASE = "CASE-11111111-1111-4111-8111-111111111111";
  const probes = [
    ["GET", "/ledger/cases/%zz", T],
    ["GET", "/ledger/cases/%zz", undefined],
    ["GET", "/ledger/models/%zz/1.0.0", T],
    ["GET", "/ledger/artifacts/%", T],
    ["GET", `/ledger/models/${"m".repeat(100)}/1.0.0`, T],
    ["GET", `/ledger/models/${"m".repeat(101)}/1.0.0`, T],
    ["GET", `/ledger/models/ecg-cnn/${"1".repeat(101)}`, T],
    ["GET", `/ledger/cases/${CASE}/`, T],
    ["GET", `//ledger/cases/${CASE}`, T],
    ["GET", `/ledger/cases/${CASE}?x=1`, T],
    ["HEAD", `/ledger/cases/${CASE}`, T],
    ["GET", `/LEDGER/cases/${CASE}`, T],
    ["OPTIONS", `/ledger/models`, T],
    ["PUT", `/ledger/models`, T],
  ];
  for (const [method, url, token] of probes) {
    const res = await app.inject({ method, url, headers: token ? { "x-agent-token": token } : {} });
    console.log(method, url.length > 70 ? url.slice(0, 30) + "…(" + url.length + ")" : url, "->", res.statusCode, res.body.slice(0, 110));
  }
  await app.close();
})();
