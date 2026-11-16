import * as crypto from "node:crypto";
import { promises as fs } from "node:fs";
import * as path from "node:path";

import * as grpc from "@grpc/grpc-js";
import { connect, hash, signers, type Gateway } from "@hyperledger/fabric-gateway";

import { envSetting } from "./settings";

const IDENTITY_NAME = /^[a-z0-9-]+$/;
const CALL_DEADLINE_MS = 30_000;

export interface ArtifactLedger {
  create(identity: string, payload: string): Promise<string>;
  read(identity: string, artifactId: string): Promise<string>;
  close(): void;
}

export interface LedgerSettings {
  walletDir: string;
  peerEndpoint: string;
  peerTlsCert: string;
  channelName: string;
  chaincodeName: string;
}

interface Session {
  gateway: Gateway;
  client: grpc.Client;
}

/** Environment first, then the defaults of the test network. Empty counts as unset. */
export function ledgerSettingsFromEnvironment(): LedgerSettings {
  const walletDir = envSetting("WALLET_DIR", path.resolve(__dirname, "../../fabric/wallet"));
  return {
    walletDir,
    // localhost, not an IP: the peer certificate lists DNS names only.
    peerEndpoint: envSetting("PEER_ENDPOINT", "localhost:18051"),
    peerTlsCert: envSetting("PEER_TLS_CERT", path.join(walletDir, "peer0-org1-tls-ca.crt")),
    channelName: envSetting("CHANNEL_NAME", "medtrace"),
    chaincodeName: envSetting("CHAINCODE_NAME", "provenance"),
  };
}

function identityHome(walletDir: string, identity: string): string {
  if (!IDENTITY_NAME.test(identity)) {
    throw new Error("identity contains unsupported characters");
  }
  const root = path.resolve(walletDir);
  const home = path.resolve(root, identity);
  if (home !== root && !home.startsWith(root + path.sep)) {
    throw new Error("identity contains unsupported characters");
  }
  return home;
}

async function withDeadline<T>(work: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => {
      reject(new Error("fabric call timed out"));
    }, CALL_DEADLINE_MS);
  });
  try {
    return await Promise.race([work, timeout]);
  } finally {
    if (timer !== undefined) {
      clearTimeout(timer);
    }
  }
}

/**
 * Fail at start-up, with the identity named, instead of at the first request of that agent
 * (which would answer 502 for a wallet that was never complete).
 */
export async function assertEnrolled(
  walletDir: string,
  identities: readonly string[],
): Promise<void> {
  for (const identity of identities) {
    const home = identityHome(walletDir, identity);
    for (const file of ["cert.pem", "key.pem", "msp-id"]) {
      try {
        await fs.access(path.join(home, file));
      } catch {
        throw new Error(`identity ${identity} is not enrolled in the wallet (missing ${file})`);
      }
    }
  }
}

export async function connectLedger(
  settings: LedgerSettings = ledgerSettingsFromEnvironment(),
): Promise<ArtifactLedger> {
  const { walletDir, peerEndpoint, peerTlsCert, channelName, chaincodeName } = settings;
  const tlsRoot = await fs.readFile(peerTlsCert);
  // The map holds the pending creation, not the finished session: requests that arrive while
  // the first one reads the wallet share its result instead of each opening a channel.
  const sessions = new Map<string, Promise<Session>>();
  const opened: Session[] = [];
  let closed = false;

  async function openSession(identity: string): Promise<Session> {
    const home = identityHome(walletDir, identity);
    const certificate = await fs.readFile(path.join(home, "cert.pem"));
    const privateKeyPem = await fs.readFile(path.join(home, "key.pem"));
    const mspId = (await fs.readFile(path.join(home, "msp-id"), "utf8")).trim();
    if (closed) {
      // close() ran while the wallet was being read: open no channel nobody will close.
      throw new Error("ledger connection is closed");
    }
    const signer = signers.newPrivateKeySigner(crypto.createPrivateKey(privateKeyPem));
    const client = new grpc.Client(peerEndpoint, grpc.credentials.createSsl(tlsRoot));
    const gateway = connect({
      client,
      identity: { mspId, credentials: certificate },
      signer,
      hash: hash.sha256,
    });
    const session = { gateway, client };
    opened.push(session);
    return session;
  }

  function sessionFor(identity: string): Promise<Session> {
    if (closed) {
      return Promise.reject(new Error("ledger connection is closed"));
    }
    const existing = sessions.get(identity);
    if (existing !== undefined) {
      return existing;
    }
    const created = openSession(identity);
    sessions.set(identity, created);
    // A failed creation (unknown identity, unreadable key) must not be cached for good.
    created.catch(() => {
      if (sessions.get(identity) === created) {
        sessions.delete(identity);
      }
    });
    return created;
  }

  return {
    async create(identity: string, payload: string): Promise<string> {
      const { gateway } = await sessionFor(identity);
      const contract = gateway.getNetwork(channelName).getContract(chaincodeName, "Provenance");
      const result = await withDeadline(
        contract.submitTransaction("CreateArtifactRecord", payload),
      );
      return Buffer.from(result).toString("utf8");
    },
    async read(identity: string, artifactId: string): Promise<string> {
      const { gateway } = await sessionFor(identity);
      const contract = gateway.getNetwork(channelName).getContract(chaincodeName, "Provenance");
      const result = await withDeadline(
        contract.evaluateTransaction("GetArtifactRecord", artifactId),
      );
      return Buffer.from(result).toString("utf8");
    },
    close(): void {
      closed = true;
      for (const session of opened) {
        session.gateway.close();
        session.client.close();
      }
      opened.length = 0;
      sessions.clear();
    },
  };
}
