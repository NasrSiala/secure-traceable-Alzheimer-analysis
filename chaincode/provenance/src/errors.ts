export type ChaincodeErrorCode = "SCHEMA" | "DUPLICATE" | "FORBIDDEN" | "NOT_FOUND";

export function fail(code: ChaincodeErrorCode, detail: string): never {
  throw new Error(`${code}: ${detail}`);
}
