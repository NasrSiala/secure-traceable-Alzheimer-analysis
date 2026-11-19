import { isErrorEnvelope } from "../src/errors";

// The Gateway client reports a chaincode refusal in these two shapes (observed on the test
// network): in `details[]` for a submit, in `message` for an evaluate.
export function submitRefusal(code: string, detail: string): Error {
  return Object.assign(
    new Error("10 ABORTED: failed to endorse transaction, see attached details for more info"),
    { details: [{ message: `chaincode response 500, ${code}: ${detail}` }] },
  );
}

export function evaluateRefusal(code: string, detail: string): Error {
  return new Error(
    `2 UNKNOWN: evaluate call to endorser returned error: chaincode response 500, ${code}: ${detail}`,
  );
}

export async function call(
  base: string,
  method: "GET" | "POST" | "DELETE",
  url: string,
  token: string | undefined,
  payload?: Record<string, unknown>,
): Promise<{ status: number; body: unknown }> {
  const headers: Record<string, string> = {};
  if (token !== undefined) {
    headers["X-Agent-Token"] = token;
  }
  if (payload !== undefined) {
    headers["content-type"] = "application/json";
  }
  const response = await fetch(`${base}${url}`, {
    method,
    headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  return { status: response.status, body: (await response.json()) as unknown };
}

export async function callRaw(
  base: string,
  url: string,
  headers: Record<string, string>,
  body: string,
): Promise<{ status: number; body: unknown }> {
  const response = await fetch(`${base}${url}`, { method: "POST", headers, body });
  return { status: response.status, body: (await response.json()) as unknown };
}

export function codeOf(body: unknown): string {
  return isErrorEnvelope(body) ? body.error.code : "";
}
