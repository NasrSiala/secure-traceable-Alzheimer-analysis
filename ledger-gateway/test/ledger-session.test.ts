import type { ConnectOptions } from "@hyperledger/fabric-gateway";

import { connectLedger, type LedgerSession } from "../src/fabric-client";
import { enroll, walletSettings } from "./wallet-fixture";

// What each session method asks of the Gateway client: which identity signs, which channel,
// chaincode and contract, which transaction, with which arguments, and whether it is submitted
// (endorsed and committed) or only evaluated. The Fabric suite proves the answers on a real
// network, which takes minutes; a wrong name or a submit that became an evaluate is caught here.

jest.setTimeout(20_000);

interface Call {
  mspId: string;
  channel: string;
  chaincode: string;
  contract: string | undefined;
  kind: "submit" | "evaluate";
  transaction: string;
  args: string[];
}

const mockCalls: Call[] = [];
const mockOutcome: { failure?: Error } = {};

const mockConnect = jest.fn((options: ConnectOptions) => ({
  getNetwork: (channel: string) => ({
    getContract: (chaincode: string, contract?: string) => {
      const answer = (kind: Call["kind"], transaction: string, args: string[]) => {
        mockCalls.push({
          mspId: options.identity.mspId,
          channel,
          chaincode,
          contract,
          kind,
          transaction,
          args,
        });
        if (mockOutcome.failure !== undefined) {
          return Promise.reject(mockOutcome.failure);
        }
        return Promise.resolve(Buffer.from(`reply of ${transaction}`));
      };
      return {
        submitTransaction: (transaction: string, ...args: string[]) =>
          answer("submit", transaction, args),
        evaluateTransaction: (transaction: string, ...args: string[]) =>
          answer("evaluate", transaction, args),
      };
    },
  }),
  close: () => undefined,
}));

jest.mock("@hyperledger/fabric-gateway", () => ({
  ...jest.requireActual<typeof import("@hyperledger/fabric-gateway")>(
    "@hyperledger/fabric-gateway",
  ),
  connect: (options: ConnectOptions) => mockConnect(options),
}));

const CASE_ID = "CASE-33333333-3333-4333-8333-333333333333";
const ARTIFACT_ID = "11111111-1111-4111-8111-111111111111";
const ARTIFACT_BODY = '{"artifactId":"11111111-1111-4111-8111-111111111111"}';
const MODEL_BODY = '{"name":"ecg-cnn","version":"1.0.0"}';

let ledger: LedgerSession | undefined;

async function open(): Promise<LedgerSession> {
  const settings = await walletSettings();
  await enroll(settings.walletDir, "verifier", "Org2MSP");
  ledger = await connectLedger(settings);
  return ledger;
}

beforeEach(() => {
  mockCalls.length = 0;
  mockConnect.mockClear();
  delete mockOutcome.failure;
});

afterEach(() => {
  ledger?.close();
  ledger = undefined;
});

describe("the five session methods", () => {
  test.each<[string, (session: LedgerSession) => Promise<string>, Call["kind"], string, string[]]>([
    [
      "create",
      (session) => session.create("agent-ingestion", ARTIFACT_BODY),
      "submit",
      "CreateArtifactRecord",
      [ARTIFACT_BODY],
    ],
    [
      "read",
      (session) => session.read("agent-ingestion", ARTIFACT_ID),
      "evaluate",
      "GetArtifactRecord",
      [ARTIFACT_ID],
    ],
    [
      "history",
      (session) => session.history("agent-ingestion", CASE_ID),
      "evaluate",
      "GetCaseHistory",
      [CASE_ID],
    ],
    [
      "registerModel",
      (session) => session.registerModel("agent-ingestion", MODEL_BODY),
      "submit",
      "RegisterModel",
      [MODEL_BODY],
    ],
    [
      "getModel",
      (session) => session.getModel("agent-ingestion", "ecg-cnn", "1.0.0"),
      "evaluate",
      "GetModel",
      ["ecg-cnn", "1.0.0"],
    ],
  ])("%s calls one transaction, in the right way", async (_name, call, kind, transaction, args) => {
    const session = await open();

    const reply = await call(session);

    expect(reply).toBe(`reply of ${transaction}`);
    expect(mockCalls).toEqual([
      {
        mspId: "Org1MSP",
        channel: "medtrace",
        chaincode: "provenance",
        contract: "Provenance",
        kind,
        transaction,
        args,
      },
    ]);
  });

  test("the identity picks the certificate that signs", async () => {
    const session = await open();

    await session.getModel("verifier", "ecg-cnn", "1.0.0");
    await session.getModel("agent-ingestion", "ecg-cnn", "1.0.0");

    expect(mockCalls.map((call) => call.mspId)).toEqual(["Org2MSP", "Org1MSP"]);
  });

  test("one identity keeps one session across methods", async () => {
    const session = await open();

    await session.registerModel("agent-ingestion", MODEL_BODY);
    await session.getModel("agent-ingestion", "ecg-cnn", "1.0.0");
    await session.history("agent-ingestion", CASE_ID);

    expect(mockConnect).toHaveBeenCalledTimes(1);
  });

  test("the channel and the chaincode come from the settings", async () => {
    const settings = { ...(await walletSettings()), channelName: "other", chaincodeName: "other-cc" };
    ledger = await connectLedger(settings);

    await ledger.history("agent-ingestion", CASE_ID);

    expect(mockCalls[0]).toMatchObject({ channel: "other", chaincode: "other-cc" });
  });

  test.each<[string, (session: LedgerSession) => Promise<string>]>([
    ["create", (session) => session.create("agent-ingestion", ARTIFACT_BODY)],
    ["read", (session) => session.read("agent-ingestion", ARTIFACT_ID)],
    ["history", (session) => session.history("agent-ingestion", CASE_ID)],
    ["registerModel", (session) => session.registerModel("agent-ingestion", MODEL_BODY)],
    ["getModel", (session) => session.getModel("agent-ingestion", "ecg-cnn", "1.0.0")],
  ])("%s lets the refusal of the peer through untouched", async (_name, call) => {
    const session = await open();
    mockOutcome.failure = new Error("10 ABORTED: chaincode response 500, FORBIDDEN: no role");

    await expect(call(session)).rejects.toBe(mockOutcome.failure);
  });
});
