import { fail } from "./errors";

export const ARTIFACT_TYPES = [
  "original",
  "processed",
  "features",
  "prediction",
  "validation",
  "explanation",
  "final_result",
] as const;

export type ArtifactType = (typeof ARTIFACT_TYPES)[number];

const ARTIFACT_TYPE_SET = new Set<string>(ARTIFACT_TYPES);

const CLIENT_FIELDS = new Set<string>([
  "artifactId",
  "caseId",
  "artifactType",
  "sha256",
  "createdAt",
  "softwareVersion",
  "modelVersion",
  "parentArtifactId",
  "offchainRef",
]);

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const CASE_ID = /^CASE-[0-9a-f-]{36}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const ISO_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d{1,9})?Z$/;

export interface ArtifactRecord {
  docType: "artifact";
  artifactId: string;
  caseId: string;
  artifactType: ArtifactType;
  sha256: string;
  createdAt: string;
  txTimestamp: string;
  softwareVersion: string;
  modelVersion: string | null;
  parentArtifactId: string | null;
  offchainRef: string;
  creatorMspId: string;
  creatorId: string;
  creatorAgent: string;
}

export interface CallerIdentity {
  mspId: string;
  subject: string;
  role: string | null;
  agent: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    fail("SCHEMA", `${field} must be a string`);
  }
  return value;
}

export function requireUuid(value: unknown, field: string): string {
  const text = requireString(value, field);
  if (!UUID.test(text)) {
    fail("SCHEMA", `${field} must be a lowercase uuid`);
  }
  return text;
}

function boundedString(value: unknown, field: string): string {
  const text = requireString(value, field);
  if (text.length < 1 || text.length > 64) {
    fail("SCHEMA", `${field} must contain 1 to 64 characters`);
  }
  return text;
}

function isIsoUtc(value: string): boolean {
  const match = ISO_UTC.exec(value);
  if (match === null) {
    return false;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return false;
  }
  return (
    parsed.getUTCFullYear() === Number(match[1]) &&
    parsed.getUTCMonth() + 1 === Number(match[2]) &&
    parsed.getUTCDate() === Number(match[3]) &&
    parsed.getUTCHours() === Number(match[4]) &&
    parsed.getUTCMinutes() === Number(match[5]) &&
    parsed.getUTCSeconds() === Number(match[6])
  );
}

export function parseClientArtifact(json: string): Omit<
  ArtifactRecord,
  "docType" | "txTimestamp" | "creatorMspId" | "creatorId" | "creatorAgent"
> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json) as unknown;
  } catch {
    fail("SCHEMA", "artifact JSON is not valid");
  }
  if (!isRecord(parsed)) {
    fail("SCHEMA", "artifact must be a JSON object");
  }
  for (const field of Object.keys(parsed)) {
    if (!CLIENT_FIELDS.has(field)) {
      fail("SCHEMA", `unknown field ${field}`);
    }
  }
  for (const field of CLIENT_FIELDS) {
    if (field !== "modelVersion" && !Object.prototype.hasOwnProperty.call(parsed, field)) {
      fail("SCHEMA", `missing field ${field}`);
    }
  }

  const artifactId = requireUuid(parsed.artifactId, "artifactId");
  const caseId = requireString(parsed.caseId, "caseId");
  if (!CASE_ID.test(caseId)) {
    fail("SCHEMA", "caseId must match CASE- and 36 lowercase hex or hyphen characters");
  }
  const artifactType = requireString(parsed.artifactType, "artifactType");
  if (!ARTIFACT_TYPE_SET.has(artifactType)) {
    fail("SCHEMA", "artifactType is not in the artifact_type list");
  }
  const sha256 = requireString(parsed.sha256, "sha256");
  if (!SHA256.test(sha256)) {
    fail("SCHEMA", "sha256 must be 64 lowercase hex characters");
  }
  const createdAt = requireString(parsed.createdAt, "createdAt");
  if (!isIsoUtc(createdAt)) {
    fail("SCHEMA", "createdAt must be ISO 8601 UTC");
  }
  const softwareVersion = boundedString(parsed.softwareVersion, "softwareVersion");

  let modelVersion: string | null = null;
  if (Object.prototype.hasOwnProperty.call(parsed, "modelVersion") && parsed.modelVersion !== null) {
    modelVersion = boundedString(parsed.modelVersion, "modelVersion");
  }

  let parentArtifactId: string | null = null;
  if (parsed.parentArtifactId !== null) {
    parentArtifactId = requireUuid(parsed.parentArtifactId, "parentArtifactId");
  }

  const offchainRef = requireString(parsed.offchainRef, "offchainRef");
  if (offchainRef !== `artifact://${artifactId}`) {
    fail("SCHEMA", "offchainRef must be artifact:// followed by artifactId");
  }

  return {
    artifactId,
    caseId,
    artifactType: artifactType as ArtifactType,
    sha256,
    createdAt,
    softwareVersion,
    modelVersion,
    parentArtifactId,
    offchainRef,
  };
}

export function certificateSubject(identityId: string): string {
  const parts = identityId.split("::");
  if (parts.length < 3 || parts[0] !== "x509") {
    fail("SCHEMA", "caller certificate subject is unavailable");
  }
  const subject = parts.slice(1, -1).join("::");
  if (subject === "") {
    fail("SCHEMA", "caller certificate subject is unavailable");
  }
  return subject;
}

export function requirePipelineAgent(caller: CallerIdentity): string {
  if (caller.role !== "pipeline-agent" || caller.agent === null || caller.agent === "") {
    fail("FORBIDDEN", "CreateArtifactRecord requires role pipeline-agent");
  }
  return caller.agent;
}
