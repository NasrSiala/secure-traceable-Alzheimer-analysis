export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: Record<string, never>;
  };
}

/** What an operator needs to tell a stopped peer from a bad channel or a commit conflict. */
export interface FailureReport {
  operation: string;
  status: number;
  cause: string;
}

const CHAINCODE_STATUS: Readonly<Record<string, number>> = {
  SCHEMA: 400,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  DUPLICATE: 409,
  PARENT_MISSING: 422,
};

// The Gateway client reports a chaincode refusal as `chaincode response 500, <CODE>: <detail>`,
// in `details[]` for a submit and in `message` for an evaluate. The prefix matters: gRPC status
// names such as `5 NOT_FOUND: ...` also end in a colon and are not an answer about the record.
const CHAINCODE_CODE =
  /chaincode response \d+, (PARENT_MISSING|DUPLICATE|FORBIDDEN|NOT_FOUND|SCHEMA):\s*([^\n]+)/;

const CAUSE_LIMIT = 400;

export function errorBody(code: string, message: string): ErrorEnvelope {
  return { error: { code, message, details: {} } };
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const error = (value as { error?: unknown }).error;
  if (typeof error !== "object" || error === null || Array.isArray(error)) {
    return false;
  }
  const body = error as { code?: unknown; message?: unknown; details?: unknown };
  return (
    typeof body.code === "string" &&
    body.code !== "" &&
    typeof body.message === "string" &&
    body.message !== "" &&
    typeof body.details === "object" &&
    body.details !== null &&
    !Array.isArray(body.details) &&
    Object.keys(body.details).length === 0
  );
}

// A submit that fails at endorsement reports the chaincode's refusal only in `details[]`
// (`message` just says "see attached details"); an evaluate puts it in `message`.
function detailMessages(error: Error): string[] {
  const details = (error as { details?: { message?: unknown }[] }).details;
  if (!Array.isArray(details)) {
    return [];
  }
  return details.flatMap((item) =>
    typeof item?.message === "string" && item.message !== "" ? [item.message] : [],
  );
}

function collectedText(error: unknown): string {
  if (!(error instanceof Error)) {
    return "";
  }
  return [error.message, ...detailMessages(error)].join("\n");
}

/**
 * One line, no request body and no header: the error class, its gRPC or commit code, the first
 * line of its message and the first line of each endorsement detail (the Gateway client puts
 * addresses, status names and the chaincode's refusal there).
 */
export function describeCause(error: unknown): string {
  if (!(error instanceof Error)) {
    return "unknown error";
  }
  const code = (error as { code?: unknown }).code;
  const label = typeof code === "number" || typeof code === "string" ? ` code=${String(code)}` : "";
  const lines = [error.message, ...detailMessages(error)].map((text) => text.split("\n")[0] ?? "");
  return `${error.name}${label}: ${[...new Set(lines)].join(" | ")}`.slice(0, CAUSE_LIMIT);
}

export function chaincodeFailure(error: unknown): { status: number; body: ErrorEnvelope } {
  const matched = CHAINCODE_CODE.exec(collectedText(error));
  if (matched === null) {
    return {
      status: 502,
      body: errorBody("UNAVAILABLE", "registre injoignable"),
    };
  }
  const code = matched[1] ?? "";
  const detail = (matched[2] ?? "").trim();
  const status = CHAINCODE_STATUS[code];
  if (status === undefined || detail === "") {
    return {
      status: 502,
      body: errorBody("UNAVAILABLE", "registre injoignable"),
    };
  }
  return { status, body: errorBody(code, detail) };
}
