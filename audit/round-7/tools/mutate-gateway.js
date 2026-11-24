// Audit helper, runs inside the container in a copy of ledger-gateway: apply each mutation to
// the copy, compile and run Jest, report killed or SURVIVED, restore.
const fs = require("fs");
const { spawnSync } = require("child_process");
const mutations = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const only = process.argv[3] ? process.argv[3].split(",") : null;
function run() {
  const t = spawnSync("node", ["node_modules/typescript/bin/tsc", "-p", "tsconfig.test.json"], { encoding: "utf8" });
  if (t.status !== 0) return { compiled: false, text: (t.stdout || "").split("\n").slice(0, 2).join(" ") };
  const j = spawnSync("node", ["node_modules/jest/bin/jest.js", "--runInBand", "--silent"], { encoding: "utf8" });
  const m = /Tests:\s+(?:(\d+) failed, )?(\d+) passed/.exec(j.stderr + j.stdout);
  return { compiled: true, failed: m && m[1] ? Number(m[1]) : 0, status: j.status };
}
fs.rmSync("dist-test", { recursive: true, force: true });
const base = run();
console.log("unmutated:", JSON.stringify(base));
mutations.forEach((mu, index) => {
  if (only && !only.includes(String(index + 1))) return;
  const original = fs.readFileSync(mu.file, "utf8");
  if (!original.includes(mu.old)) { console.log(`NOT APPLIED  #${index + 1} ${mu.label}`); return; }
  fs.writeFileSync(mu.file, original.replace(mu.old, mu.new));
  const r = run();
  const verdict = !r.compiled ? "killed(compile)" : r.status !== 0 ? `killed(${r.failed})` : "SURVIVED";
  console.log(`${verdict.padEnd(16)} #${index + 1} ${mu.label}`);
  fs.writeFileSync(mu.file, original);
});
