import { buildApp } from "./app";
import { type FailureReport } from "./errors";
import { assertEnrolled, connectLedger, ledgerSettingsFromEnvironment } from "./fabric-client";
import { envSetting } from "./settings";
import { loadTokenDirectory } from "./tokens";

function logFailure(report: FailureReport): void {
  process.stderr.write(`${JSON.stringify({ event: "ledger-failure", ...report })}\n`);
}

function listeningPort(text: string): number {
  if (!/^\d+$/.test(text)) {
    throw new Error("GATEWAY_PORT is invalid");
  }
  const port = Number(text);
  if (port > 65535) {
    throw new Error("GATEWAY_PORT is invalid");
  }
  return port;
}

async function main(): Promise<void> {
  const tokenFile = envSetting("AGENT_TOKEN_FILE", "");
  if (tokenFile === "") {
    throw new Error("AGENT_TOKEN_FILE is required");
  }
  const host = envSetting("GATEWAY_HOST", "127.0.0.1");
  const port = listeningPort(envSetting("GATEWAY_PORT", "8080"));
  const tokens = await loadTokenDirectory(tokenFile);
  const settings = ledgerSettingsFromEnvironment();
  await assertEnrolled(settings.walletDir, tokens.identities());
  const ledger = await connectLedger(settings);
  const app = buildApp({ tokens, ledger, onFailure: logFailure });
  try {
    const address = await app.listen({ host, port });
    process.stdout.write(`ledger-gateway listening on ${address}\n`);
  } catch (error) {
    ledger.close();
    throw error;
  }
  const shutdown = (): void => {
    app
      .close()
      .catch((error: unknown) => {
        process.stderr.write(`${error instanceof Error ? error.message : "close failed"}\n`);
        process.exitCode = 1;
      })
      .finally(() => {
        ledger.close();
      });
  };
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "gateway failed";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
