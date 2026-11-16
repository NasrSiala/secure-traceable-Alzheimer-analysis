import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

import { loadTokenDirectory, TokenDirectory, tokensForWallet } from "../src/tokens";

const TOKEN_A = "a".repeat(32);
const TOKEN_B = "b".repeat(32);

async function tokenFile(content: string): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), "saam-tokens-"));
  const file = path.join(dir, "agent-tokens.json");
  await writeFile(file, content, "utf8");
  return file;
}

describe("TokenDirectory", () => {
  test("maps a token to its Fabric identity", () => {
    const tokens = TokenDirectory.fromPairs([
      [TOKEN_A, "agent-ingestion"],
      [TOKEN_B, "verifier"],
    ]);

    expect(tokens.identityFor(TOKEN_A)).toBe("agent-ingestion");
    expect(tokens.tokenFor("verifier")).toBe(TOKEN_B);
  });

  test("rejects an unknown, empty, or missing token", () => {
    const tokens = TokenDirectory.fromPairs([[TOKEN_A, "agent-ingestion"]]);

    expect(tokens.identityFor("c".repeat(32))).toBeNull();
    expect(tokens.identityFor("short")).toBeNull();
    expect(tokens.identityFor("")).toBeNull();
    expect(tokens.identityFor(undefined)).toBeNull();
  });

  test("rejects a token that only starts like a real one", () => {
    const tokens = TokenDirectory.fromPairs([[TOKEN_A, "agent-ingestion"]]);

    expect(tokens.identityFor(`${TOKEN_A}x`)).toBeNull();
    expect(tokens.identityFor(TOKEN_A.slice(1))).toBeNull();
  });

  test("rejects a path-like identity and a duplicate token", () => {
    expect(() => TokenDirectory.fromPairs([[TOKEN_A, "../agent-ingestion"]])).toThrow(
      "unsupported characters",
    );
    expect(() =>
      TokenDirectory.fromPairs([
        [TOKEN_A, "agent-ingestion"],
        [TOKEN_A, "verifier"],
      ]),
    ).toThrow("ambiguous");
  });

  test("rejects one identity with two tokens", () => {
    expect(() =>
      TokenDirectory.fromPairs([
        [TOKEN_A, "agent-ingestion"],
        [TOKEN_B, "agent-ingestion"],
      ]),
    ).toThrow("ambiguous");
  });

  test("rejects a short token and a token with a line break, each with its own message", () => {
    expect(() => TokenDirectory.fromPairs([["short", "agent-ingestion"]])).toThrow("too short");
    expect(() =>
      TokenDirectory.fromPairs([[`${"a".repeat(20)}\nX-Evil: 1`, "agent-ingestion"]]),
    ).toThrow("line break");
  });

  test("lists the identities it holds a token for", () => {
    const tokens = TokenDirectory.fromPairs([
      [TOKEN_A, "agent-ingestion"],
      [TOKEN_B, "verifier"],
    ]);

    expect(tokens.identities().sort()).toEqual(["agent-ingestion", "verifier"]);
  });

  test("asks for the token of an identity that is not known", () => {
    const tokens = TokenDirectory.fromPairs([[TOKEN_A, "agent-ingestion"]]);

    expect(() => tokens.tokenFor("verifier")).toThrow("not in the wallet");
  });

  test("loads a token file", async () => {
    const file = await tokenFile(JSON.stringify({ "agent-ingestion": TOKEN_A, verifier: TOKEN_B }));

    const tokens = await loadTokenDirectory(file);

    expect(tokens.identityFor(TOKEN_A)).toBe("agent-ingestion");
    expect(tokens.identityFor(TOKEN_B)).toBe("verifier");
  });

  test.each([
    ["text that is not JSON", "not json", "not valid JSON"],
    ["a JSON array", JSON.stringify([TOKEN_A]), "must be a JSON object"],
    ["a JSON string", JSON.stringify(TOKEN_A), "must be a JSON object"],
    ["a token that is not a string", JSON.stringify({ "agent-ingestion": 7 }), "identities to tokens"],
    ["a short token", JSON.stringify({ "agent-ingestion": "short" }), "too short"],
    ["a path-like identity", JSON.stringify({ "../x": TOKEN_A }), "unsupported characters"],
  ])("refuses %s without echoing the file", async (_label, content, message) => {
    const file = await tokenFile(content);

    const failure = await loadTokenDirectory(file).then(
      () => undefined,
      (error: unknown) => error as Error,
    );

    expect(failure?.message).toContain(message);
    expect(failure?.message).not.toContain(TOKEN_A);
    expect(failure?.message).not.toContain(file);
  });

  test("refuses a missing token file without echoing its path", async () => {
    const file = path.join(tmpdir(), "saam-no-such-dir", "agent-tokens.json");

    const failure = await loadTokenDirectory(file).then(
      () => undefined,
      (error: unknown) => error as Error,
    );

    expect(failure?.message).toBe("AGENT_TOKEN_FILE is not valid JSON");
  });
});

describe("tokensForWallet", () => {
  test("gives a fresh token to each enrolled identity and to no other folder", async () => {
    const wallet = await mkdtemp(path.join(tmpdir(), "saam-wallet-"));
    await mkdir(path.join(wallet, "agent-ingestion"));
    await writeFile(path.join(wallet, "agent-ingestion", "cert.pem"), "x");
    await mkdir(path.join(wallet, "verifier"));
    await writeFile(path.join(wallet, "verifier", "cert.pem"), "x");
    await mkdir(path.join(wallet, "half-enrolled"));
    await mkdir(path.join(wallet, "Not_An_Identity"));
    await writeFile(path.join(wallet, "Not_An_Identity", "cert.pem"), "x");
    await writeFile(path.join(wallet, "peer0-org1-tls-ca.crt"), "x");

    const tokens = await tokensForWallet(wallet);
    const ingestion = tokens.tokenFor("agent-ingestion");

    expect(tokens.identityFor(ingestion)).toBe("agent-ingestion");
    expect(tokens.identityFor(tokens.tokenFor("verifier"))).toBe("verifier");
    expect(ingestion).toMatch(/^[0-9a-f]{64}$/);
    expect(() => tokens.tokenFor("half-enrolled")).toThrow("not in the wallet");
    expect(() => tokens.tokenFor("Not_An_Identity")).toThrow("not in the wallet");
    expect((await tokensForWallet(wallet)).tokenFor("agent-ingestion")).not.toBe(ingestion);
  });

  test("refuses a wallet with no identity", async () => {
    const wallet = await mkdtemp(path.join(tmpdir(), "saam-wallet-"));

    await expect(tokensForWallet(wallet)).rejects.toThrow("wallet has no identities");
  });
});
