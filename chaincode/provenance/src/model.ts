import { type CallerIdentity, isRecord, requireString, SHA256 } from "./artifact";
import { fail } from "./errors";

// MODEL (Schema 5.2): key = composite key `model` (name, version). Name, version and framework
// follow the `models` table of schema.sql, so a row and its record accept the same values.
export const MODEL_KEY = "model";

const CLIENT_FIELDS = new Set<string>(["name", "version", "sha256", "framework"]);

const NAME = /^[a-z0-9_-]{1,60}$/;
const VERSION = /^[0-9]+\.[0-9]+\.[0-9]+$/;

export interface ModelRecord {
  docType: "model";
  name: string;
  version: string;
  sha256: string;
  framework: string;
  registeredAt: string;
  registeredBy: string;
}

export type ClientModel = Omit<ModelRecord, "docType" | "registeredAt" | "registeredBy">;

// Both names are composite key attributes: a value outside these patterns (a null byte above
// all) is a SCHEMA refusal here, never an untyped error from the stub.
export function requireModelName(value: unknown): string {
  const text = requireString(value, "name");
  if (!NAME.test(text)) {
    fail("SCHEMA", "name must be 1 to 60 characters among a-z, 0-9, underscore and hyphen");
  }
  return text;
}

export function requireModelVersion(value: unknown): string {
  const text = requireString(value, "version");
  if (!VERSION.test(text)) {
    fail("SCHEMA", "version must be three dot-separated numbers");
  }
  return text;
}

function requireFramework(value: unknown): string {
  const text = requireString(value, "framework");
  if (text.length < 1 || text.length > 40) {
    fail("SCHEMA", "framework must contain 1 to 40 characters");
  }
  return text;
}

export function parseClientModel(json: string): ClientModel {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json) as unknown;
  } catch {
    fail("SCHEMA", "model JSON is not valid");
  }
  if (!isRecord(parsed)) {
    fail("SCHEMA", "model must be a JSON object");
  }
  for (const field of Object.keys(parsed)) {
    if (!CLIENT_FIELDS.has(field)) {
      fail("SCHEMA", `unknown field ${field}`);
    }
  }
  for (const field of CLIENT_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(parsed, field)) {
      fail("SCHEMA", `missing field ${field}`);
    }
  }

  const sha256 = requireString(parsed.sha256, "sha256");
  if (!SHA256.test(sha256)) {
    fail("SCHEMA", "sha256 must be 64 lowercase hex characters");
  }
  return {
    name: requireModelName(parsed.name),
    version: requireModelVersion(parsed.version),
    sha256,
    framework: requireFramework(parsed.framework),
  };
}

export function requireModelAdmin(caller: CallerIdentity): void {
  if (caller.role !== "model-admin") {
    fail("FORBIDDEN", "RegisterModel requires role model-admin");
  }
}
