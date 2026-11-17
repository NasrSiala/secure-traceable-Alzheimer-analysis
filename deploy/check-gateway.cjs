// Le 404 attendu vient du chaincode ; un 404 de route ne suffit pas.
const fs = require("node:fs");
const http = require("node:http");
const artifactId = "00000000-0000-0000-0000-000000000000";
const tokens = JSON.parse(fs.readFileSync(process.env.AGENT_TOKEN_FILE, "utf8"));
const request = http.get(
  `http://127.0.0.1:8080/ledger/artifacts/${artifactId}`,
  { headers: { "X-Agent-Token": tokens.verifier }, timeout: 2500 },
  (response) => {
    let content = "";
    response.setEncoding("utf8");
    response.on("data", (chunk) => { content += chunk; });
    response.on("end", () => {
      try {
        const body = JSON.parse(content);
        const absent = response.statusCode === 404
          && body.error?.code === "NOT_FOUND"
          && body.error?.message === "artifactId is not on the ledger";
        const present = response.statusCode === 200
          && body.artifactId === artifactId && body.docType === "ARTIFACT";
        process.exitCode = absent || present ? 0 : 1;
      } catch {
        process.exitCode = 1;
      }
    });
  },
);
request.on("timeout", () => request.destroy());
request.on("error", () => { process.exitCode = 1; });
