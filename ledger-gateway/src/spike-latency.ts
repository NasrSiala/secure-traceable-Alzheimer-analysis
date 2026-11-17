import * as crypto from "node:crypto";
import { promises as fs } from "node:fs";
import * as path from "node:path";

import type { CallOptions } from "@grpc/grpc-js";
import * as grpc from "@grpc/grpc-js";
import { connect, hash, signers, StatusCode } from "@hyperledger/fabric-gateway";

import { probeArtifact } from "./probe-artifact";
import { envSetting } from "./settings";

const TRANSACTION_COUNT = 7;
const BUDGET_SECONDS = 7.3;
const IDENTITY = "agent-ingestion";
const CONTRACT = "Provenance";

const walletDir = envSetting("WALLET_DIR", path.resolve(__dirname, "../../fabric/wallet"));
const fabricDir = path.resolve(__dirname, "../../fabric");
const peerEndpoint = envSetting("PEER_ENDPOINT", "localhost:18051");
const peerTlsCert = envSetting("PEER_TLS_CERT", path.join(walletDir, "peer0-org1-tls-ca.crt"));
const channelName = envSetting("CHANNEL_NAME", "medtrace");
const chaincodeName = envSetting("CHAINCODE_NAME", "provenance");

interface LatencyReport {
  transactionCount: number;
  validatedCount: number;
  endorsementPolicy: string;
  channel: string;
  chaincode: string;
  contract: string;
  identity: string;
  unit: "seconds";
  measurement: "endorse-submit-commit-valid";
  percentileMethod: "nearest-rank";
  samplesSeconds: number[];
  transactionIds: string[];
  validationCodes: string[];
  blockNumbers: string[];
  p50: number;
  p95: number;
  maximum: number;
  budgetSeconds: number;
  withinBudget: boolean;
  batchTimeout: string;
  batchTimeoutDecision: "keep" | "set-to-0.5s";
}

function environmentError(message: string): Error {
  return new Error(`environment unavailable: ${message}`);
}

// The report carries two settings of this repository. fabric/spike-latency.sh passes them as
// environment variables (the container run mounts only ledger-gateway); started alone, as
// `npm run spike:latency`, the probe reads the files that define them.
async function setting(name: string, file: string, pattern: RegExp): Promise<string> {
  const fromEnvironment = process.env[name];
  if (fromEnvironment !== undefined && fromEnvironment !== "") {
    return fromEnvironment;
  }
  try {
    const text = await fs.readFile(path.join(fabricDir, file), "utf8");
    return pattern.exec(text)?.[1]?.trim() ?? "";
  } catch {
    return "";
  }
}

async function readWalletFile(file: string): Promise<Buffer> {
  try {
    return await fs.readFile(file);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      throw environmentError(
        `${file} not found. Run fabric/network.sh start, then fabric/enroll-identities.sh.`,
      );
    }
    throw error;
  }
}

function requireAndPolicy(policy: string): void {
  if (
    !policy.includes("AND") ||
    !policy.includes("Org1MSP.peer") ||
    !policy.includes("Org2MSP.peer")
  ) {
    throw environmentError("endorsement policy is not AND(Org1MSP.peer, Org2MSP.peer)");
  }
}

function roundSeconds(elapsedNanoseconds: bigint): number {
  return Math.round(Number(elapsedNanoseconds) / 1000) / 1e6;
}

function nearestRank(sortedSeconds: number[], percentile: number): number {
  const rank = Math.ceil((percentile / 100) * sortedSeconds.length);
  const index = Math.min(sortedSeconds.length, Math.max(1, rank)) - 1;
  return sortedSeconds[index] ?? 0;
}

function describe(error: unknown): string {
  if (!(error instanceof Error)) {
    return String(error);
  }
  const details = (error as { details?: { mspId?: string; message?: string }[] }).details;
  if (!Array.isArray(details) || details.length === 0) {
    return error.message;
  }
  const lines = details.map((item) => `${item.mspId ?? "peer"}: ${item.message ?? ""}`);
  return `${error.message}\n${lines.join("\n")}`;
}

async function main(): Promise<number> {
  const batchTimeout = await setting(
    "BATCH_TIMEOUT",
    "config/configtx.yaml",
    /^[ \t]*BatchTimeout:[ \t]*(\S+)/m,
  );
  const endorsementPolicy = await setting(
    "ENDORSEMENT_POLICY",
    "scripts/deploy-chaincode.sh",
    /^POLICY="(.*)"[ \t]*\r?$/m,
  );
  if (batchTimeout === "") {
    throw environmentError("BatchTimeout is unknown. Set BATCH_TIMEOUT or run fabric/spike-latency.sh.");
  }
  requireAndPolicy(endorsementPolicy);

  const home = path.join(walletDir, IDENTITY);
  const certificate = await readWalletFile(path.join(home, "cert.pem"));
  const privateKeyPem = await readWalletFile(path.join(home, "key.pem"));
  const mspId = (await readWalletFile(path.join(home, "msp-id"))).toString("utf8").trim();
  const tlsRoot = await readWalletFile(peerTlsCert);
  const signer = signers.newPrivateKeySigner(crypto.createPrivateKey(privateKeyPem));
  const client = new grpc.Client(peerEndpoint, grpc.credentials.createSsl(tlsRoot));
  const gateway = connect({
    client,
    identity: { mspId, credentials: certificate },
    signer,
    hash: hash.sha256,
  });

  const samplesSeconds: number[] = [];
  const transactionIds: string[] = [];
  const validationCodes: string[] = [];
  const blockNumbers: string[] = [];

  // CreateArtifactRecord refuses an artifactId that exists (AC-07.3), so the identifiers of a
  // run are new each time: the probe can run again on the same network.
  const runId = crypto.randomBytes(6).toString("hex");

  try {
    const contract = gateway.getNetwork(channelName).getContract(chaincodeName, CONTRACT);
    for (let index = 1; index <= TRANSACTION_COUNT; index += 1) {
      const payload = probeArtifact(`latency-${runId}-${index}`).payload;
      const call: CallOptions = { deadline: new Date(Date.now() + 60_000) };
      const started = process.hrtime.bigint();
      const proposal = contract.newProposal("CreateArtifactRecord", {
        arguments: [payload],
        endorsingOrganizations: ["Org1MSP", "Org2MSP"],
      });
      const endorsed = await proposal.endorse(call);
      const submitted = await endorsed.submit(call);
      const status = await submitted.getStatus(call);
      const elapsed = process.hrtime.bigint() - started;
      if (!status.successful || status.code !== StatusCode.VALID) {
        throw environmentError(
          `transaction ${status.transactionId} was not validated (code ${status.code})`,
        );
      }
      samplesSeconds.push(roundSeconds(elapsed));
      transactionIds.push(status.transactionId);
      validationCodes.push("VALID");
      blockNumbers.push(status.blockNumber.toString());
    }
  } finally {
    gateway.close();
    client.close();
  }

  if (samplesSeconds.length !== TRANSACTION_COUNT) {
    throw environmentError(`measured ${samplesSeconds.length} transactions, not ${TRANSACTION_COUNT}`);
  }

  const ordered = [...samplesSeconds].sort((left, right) => left - right);
  const p50 = nearestRank(ordered, 50);
  const p95 = nearestRank(ordered, 95);
  const maximum = ordered[ordered.length - 1] ?? 0;
  const withinBudget = Math.round(p95 * 1e6) <= Math.round(BUDGET_SECONDS * 1e6);
  const report: LatencyReport = {
    transactionCount: TRANSACTION_COUNT,
    validatedCount: validationCodes.length,
    endorsementPolicy,
    channel: channelName,
    chaincode: chaincodeName,
    contract: CONTRACT,
    identity: IDENTITY,
    unit: "seconds",
    measurement: "endorse-submit-commit-valid",
    percentileMethod: "nearest-rank",
    samplesSeconds,
    transactionIds,
    validationCodes,
    blockNumbers,
    p50,
    p95,
    maximum,
    budgetSeconds: BUDGET_SECONDS,
    withinBudget,
    batchTimeout,
    batchTimeoutDecision: withinBudget ? "keep" : "set-to-0.5s",
  };
  process.stdout.write(`${JSON.stringify(report)}\n`);
  if (!withinBudget) {
    process.stderr.write(
      `budget exceeded: p50=${p50}s p95=${p95}s maximum=${maximum}s budget=${BUDGET_SECONDS}s decision=set-to-0.5s\n` +
        `Run again before changing BatchTimeout (${batchTimeout}): lowering it only helps when p50 is close to it; ` +
        "one slow sample among normal ones is a stalled host.\n",
    );
    return 2;
  }
  return 0;
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error: unknown) => {
    process.stderr.write(`${describe(error)}\n`);
    process.exitCode = 1;
  });
