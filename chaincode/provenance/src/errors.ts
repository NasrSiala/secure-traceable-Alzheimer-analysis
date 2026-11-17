export type ChaincodeErrorCode =
  | "SCHEMA"
  | "DUPLICATE"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "PARENT_MISSING"
  | "INTEGRITY";

export function fail(code: ChaincodeErrorCode, detail: string): never {
  throw new Error(`${code}: ${detail}`);
}
