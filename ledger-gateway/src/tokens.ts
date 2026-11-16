import { timingSafeEqual } from "node:crypto";
import { promises as fs } from "node:fs";
import * as path from "node:path";

const IDENTITY_NAME = /^[a-z0-9-]+$/;
const MIN_TOKEN_LENGTH = 16;

export class TokenDirectory {
  private constructor(
    private readonly byToken: ReadonlyMap<string, string>,
    private readonly byIdentity: ReadonlyMap<string, string>,
  ) {}

  static fromPairs(pairs: readonly (readonly [string, string])[]): TokenDirectory {
    const byToken = new Map<string, string>();
    const byIdentity = new Map<string, string>();
    for (const [token, identity] of pairs) {
      if (!IDENTITY_NAME.test(identity)) {
        throw new Error("identity contains unsupported characters");
      }
      if (token.length < MIN_TOKEN_LENGTH) {
        throw new Error("token is too short");
      }
      if (/[\r\n]/.test(token)) {
        throw new Error("token contains a line break");
      }
      if (byToken.has(token) || byIdentity.has(identity)) {
        throw new Error("token mapping is ambiguous");
      }
      byToken.set(token, identity);
      byIdentity.set(identity, token);
    }
    return new TokenDirectory(byToken, byIdentity);
  }

  identityFor(presented: string | undefined): string | null {
    if (presented === undefined || presented === "") {
      return null;
    }
    const presentedBytes = Buffer.from(presented);
    let found: string | null = null;
    for (const [token, identity] of this.byToken) {
      const tokenBytes = Buffer.from(token);
      if (tokenBytes.length !== presentedBytes.length) {
        continue;
      }
      if (timingSafeEqual(tokenBytes, presentedBytes)) {
        found = identity;
      }
    }
    return found;
  }

  identities(): string[] {
    return [...this.byIdentity.keys()];
  }

  tokenFor(identity: string): string {
    const token = this.byIdentity.get(identity);
    if (token === undefined) {
      throw new Error("identity is not in the wallet");
    }
    return token;
  }
}

export async function tokensForWallet(walletDir: string): Promise<TokenDirectory> {
  const { randomBytes } = await import("node:crypto");
  const entries = await fs.readdir(walletDir, { withFileTypes: true });
  const pairs: (readonly [string, string])[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || !IDENTITY_NAME.test(entry.name)) {
      continue;
    }
    try {
      await fs.access(path.join(walletDir, entry.name, "cert.pem"));
    } catch {
      continue;
    }
    pairs.push([randomBytes(32).toString("hex"), entry.name]);
  }
  if (pairs.length === 0) {
    throw new Error("wallet has no identities");
  }
  return TokenDirectory.fromPairs(pairs);
}

export async function loadTokenDirectory(filePath: string): Promise<TokenDirectory> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await fs.readFile(filePath, "utf8")) as unknown;
  } catch {
    throw new Error("AGENT_TOKEN_FILE is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("AGENT_TOKEN_FILE must be a JSON object");
  }
  const pairs: (readonly [string, string])[] = [];
  for (const [identity, token] of Object.entries(parsed)) {
    if (typeof token !== "string") {
      throw new Error("AGENT_TOKEN_FILE must map identities to tokens");
    }
    pairs.push([token, identity]);
  }
  return TokenDirectory.fromPairs(pairs);
}
