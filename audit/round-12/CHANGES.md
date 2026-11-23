# Changes — round 12

| ID | Files | What changed | Verification |
|---|---|---|---|
| AUD-125 | `chaincode/provenance/src/provenance.ts`, `test/provenance.test.ts`, `test/model-registry.test.ts` | `GetArtifactRecord` parses with `parseStoredArtifact`. `GetModel` parses with `parseStoredModel`. Corrupt JSON is `INTEGRITY`. A valid record is returned unchanged. | `npm test` in `chaincode/provenance`: 185 passed. |
| AUD-126 | `ledger-gateway/src/app.ts`, `test/routes.test.ts` | A miss under `/ledger` without a token is 401. The same miss with a token stays 404. `/health` without a token stays 404. | `npm test` in `ledger-gateway`: 214 passed. |
