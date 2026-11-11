import { createHash } from "node:crypto";

const NAMESPACE = "6f0e8b3a-7c21-4d5e-9a10-2b6c4d8e0f11";

function uuidToBytes(uuid: string): Buffer {
  return Buffer.from(uuid.replace(/-/g, ""), "hex");
}

function formatUuid(bytes: Buffer): string {
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function artifactIdForProbe(key: string): string {
  const hash = createHash("sha1");
  hash.update(uuidToBytes(NAMESPACE));
  hash.update(key, "utf8");
  const bytes = Buffer.from(hash.digest().subarray(0, 16));
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return formatUuid(bytes);
}

export function probeArtifact(key: string): { artifactId: string; payload: string } {
  const artifactId = artifactIdForProbe(key);
  const payload = JSON.stringify({
    artifactId,
    caseId: `CASE-${artifactId}`,
    artifactType: "original",
    sha256: "ab".repeat(32),
    createdAt: "2026-11-09T12:00:00.000Z",
    softwareVersion: "0.1.0",
    modelVersion: null,
    parentArtifactId: null,
    offchainRef: `artifact://${artifactId}`,
  });
  return { artifactId, payload };
}
