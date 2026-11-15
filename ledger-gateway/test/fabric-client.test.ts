import { rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

import * as grpc from "@grpc/grpc-js";

import {
  assertEnrolled,
  connectLedger,
  ledgerSettingsFromEnvironment,
} from "../src/fabric-client";
import { envSetting } from "../src/settings";
import { enroll, walletSettings } from "./wallet-fixture";

jest.setTimeout(20_000);

const ARTIFACT_ID = "11111111-1111-4111-8111-111111111111";

describe("sessions", () => {
  let made = 0;
  let closed = 0;
  let original: PropertyDescriptor | undefined;

  beforeEach(() => {
    made = 0;
    closed = 0;
    original = Object.getOwnPropertyDescriptor(grpc, "Client");
    const Real = grpc.Client;
    class Counting extends Real {
      constructor(...args: ConstructorParameters<typeof Real>) {
        super(...args);
        made += 1;
      }

      override close(): void {
        closed += 1;
        super.close();
      }
    }
    Object.defineProperty(grpc, "Client", { value: Counting, configurable: true, writable: true });
  });

  afterEach(() => {
    if (original !== undefined) {
      Object.defineProperty(grpc, "Client", original);
    }
  });

  test("concurrent first requests for one identity share one channel (AUD-072)", async () => {
    const ledger = await connectLedger(await walletSettings());

    const results = await Promise.allSettled(
      Array.from({ length: 5 }, () => ledger.read("agent-ingestion", ARTIFACT_ID)),
    );
    ledger.close();

    expect(results.every((result) => result.status === "rejected")).toBe(true);
    expect(made).toBe(1);
    expect(closed).toBe(1);
  });

  test("a later request reuses the channel", async () => {
    const ledger = await connectLedger(await walletSettings());

    await ledger.read("agent-ingestion", ARTIFACT_ID).catch(() => undefined);
    await ledger.read("agent-ingestion", ARTIFACT_ID).catch(() => undefined);
    ledger.close();

    expect(made).toBe(1);
  });

  test("a failed session creation is tried again by the next request", async () => {
    const settings = await walletSettings();
    const ledger = await connectLedger(settings);

    const first = await ledger.read("agent-late", ARTIFACT_ID).then(
      () => undefined,
      (error: unknown) => error as NodeJS.ErrnoException,
    );
    await enroll(settings.walletDir, "agent-late");
    const second = await ledger.read("agent-late", ARTIFACT_ID).then(
      () => undefined,
      (error: unknown) => error as NodeJS.ErrnoException,
    );
    ledger.close();

    expect(first?.code).toBe("ENOENT");
    expect(second?.code).not.toBe("ENOENT");
    expect(made).toBe(1);
  });

  test("an identity outside the wallet's naming rule never reaches the file system", async () => {
    const ledger = await connectLedger(await walletSettings());

    for (const identity of ["../agent-ingestion", "Agent-Ingestion", "agent_ingestion", ""]) {
      await expect(ledger.read(identity, ARTIFACT_ID)).rejects.toThrow("unsupported characters");
    }
    ledger.close();

    expect(made).toBe(0);
  });

  test("closing while the wallet is being read opens no channel (AUD-087)", async () => {
    const ledger = await connectLedger(await walletSettings());

    const pending = ledger.read("agent-ingestion", ARTIFACT_ID);
    ledger.close();

    await expect(pending).rejects.toThrow("is closed");
    expect(made).toBe(0);
  });

  test("a closed connection refuses new requests", async () => {
    const ledger = await connectLedger(await walletSettings());
    ledger.close();

    await expect(ledger.read("agent-ingestion", ARTIFACT_ID)).rejects.toThrow("is closed");
    expect(made).toBe(0);
  });
});

describe("start-up check of the wallet (AUD-086)", () => {
  test("passes when every identity of the token file is enrolled", async () => {
    const settings = await walletSettings();
    await enroll(settings.walletDir, "verifier");

    await expect(
      assertEnrolled(settings.walletDir, ["agent-ingestion", "verifier"]),
    ).resolves.toBeUndefined();
  });

  test("names the identity and the missing file", async () => {
    const settings = await walletSettings();

    await expect(assertEnrolled(settings.walletDir, ["agent-ingestion", "agent-late"])).rejects.toThrow(
      "identity agent-late is not enrolled in the wallet (missing cert.pem)",
    );
    await rm(path.join(settings.walletDir, "agent-ingestion", "key.pem"));
    await expect(assertEnrolled(settings.walletDir, ["agent-ingestion"])).rejects.toThrow(
      "identity agent-ingestion is not enrolled in the wallet (missing key.pem)",
    );
  });

  test("refuses an identity that is not a plain name", async () => {
    const settings = await walletSettings();

    await expect(assertEnrolled(settings.walletDir, ["../agent-ingestion"])).rejects.toThrow(
      "unsupported characters",
    );
  });
});

describe("settings from the environment (AUD-073)", () => {
  const names = [
    "WALLET_DIR",
    "PEER_ENDPOINT",
    "PEER_TLS_CERT",
    "CHANNEL_NAME",
    "CHAINCODE_NAME",
    "SAAM_TEST_SETTING",
  ];
  const saved = new Map<string, string | undefined>();

  beforeEach(() => {
    for (const name of names) {
      saved.set(name, process.env[name]);
      delete process.env[name];
    }
  });

  afterEach(() => {
    for (const name of names) {
      const value = saved.get(name);
      if (value === undefined) {
        delete process.env[name];
      } else {
        process.env[name] = value;
      }
    }
  });

  test("without any variable, the test network defaults apply", () => {
    const settings = ledgerSettingsFromEnvironment();

    expect(settings.peerEndpoint).toBe("localhost:18051");
    expect(settings.channelName).toBe("medtrace");
    expect(settings.chaincodeName).toBe("provenance");
    expect(settings.walletDir).toMatch(/fabric[\\/]wallet$/);
    expect(settings.peerTlsCert).toBe(path.join(settings.walletDir, "peer0-org1-tls-ca.crt"));
  });

  test("an empty or blank variable counts as unset, as in a copied .env.example", () => {
    const defaults = ledgerSettingsFromEnvironment();
    for (const name of names) {
      process.env[name] = name === "PEER_ENDPOINT" ? "   " : "";
    }

    expect(ledgerSettingsFromEnvironment()).toEqual(defaults);
  });

  test("a value wins over the default", () => {
    process.env.WALLET_DIR = path.join(tmpdir(), "elsewhere");
    process.env.PEER_ENDPOINT = "peer0.org1.example.com:7051";
    process.env.CHANNEL_NAME = "other";

    const settings = ledgerSettingsFromEnvironment();

    expect(settings.walletDir).toBe(path.join(tmpdir(), "elsewhere"));
    expect(settings.peerEndpoint).toBe("peer0.org1.example.com:7051");
    expect(settings.channelName).toBe("other");
    expect(settings.peerTlsCert).toBe(
      path.join(tmpdir(), "elsewhere", "peer0-org1-tls-ca.crt"),
    );
  });

  test("envSetting returns the fallback for undefined, empty and blank", () => {
    expect(envSetting("SAAM_TEST_SETTING", "fallback")).toBe("fallback");
    process.env.SAAM_TEST_SETTING = "";
    expect(envSetting("SAAM_TEST_SETTING", "fallback")).toBe("fallback");
    process.env.SAAM_TEST_SETTING = " \t";
    expect(envSetting("SAAM_TEST_SETTING", "fallback")).toBe("fallback");
    process.env.SAAM_TEST_SETTING = "value";
    expect(envSetting("SAAM_TEST_SETTING", "fallback")).toBe("value");
  });

  test("envSetting trims a value (a CRLF .env leaves a carriage return)", () => {
    process.env.SAAM_TEST_SETTING = "8080\r";
    expect(envSetting("SAAM_TEST_SETTING", "fallback")).toBe("8080");
    process.env.SAAM_TEST_SETTING = "  localhost:18051 ";
    expect(envSetting("SAAM_TEST_SETTING", "fallback")).toBe("localhost:18051");
  });
});
