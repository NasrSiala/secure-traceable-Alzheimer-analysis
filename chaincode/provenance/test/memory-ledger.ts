import { Context } from "fabric-contract-api";

// An in-memory stand-in for the two things a chaincode call touches: the ledger state (stub)
// and the certificate of the caller (clientIdentity). Shared by every test file of the package.

export class MemoryStub {
  readonly data = new Map<string, Buffer>();
  readonly events: { name: string; payload: Buffer }[] = [];
  readonly history = new Map<string, {txId: string; isDelete: boolean; value: Buffer}[]>();
  now = "2026-11-09T18:00:00.000Z";

  async getState(key: string): Promise<Uint8Array> {
    return this.data.get(key) ?? Buffer.alloc(0);
  }

  async putState(key: string, value: Uint8Array): Promise<void> {
    this.data.set(key, Buffer.from(value));
    this.history.set(key, [...(this.history.get(key) ?? []), {txId: "a".repeat(64), isDelete: false, value: Buffer.from(value)}]);
  }

  async getHistoryForKey(key: string) {
    const entries = this.history.get(key) ?? [];
    let index = 0;
    return {
      next: async () => index < entries.length ? {done: false, value: entries[index++]} : {done: true},
      close: async () => undefined,
    };
  }

  getDateTimestamp(): Date {
    return new Date(this.now);
  }

  createCompositeKey(objectType: string, attributes: string[]): string {
    for (const part of [objectType, ...attributes]) {
      if (part.includes("\u0000")) {
        throw new Error("composite key attribute contains a null");
      }
    }
    let key = `\u0000${objectType}\u0000`;
    for (const attribute of attributes) {
      key += `${attribute}\u0000`;
    }
    return key;
  }

  async getStateByPartialCompositeKey(
    objectType: string,
    attributes: string[],
  ): Promise<{
    next: () => Promise<{ done?: boolean; value?: { value: Buffer } }>;
    close: () => Promise<void>;
  }> {
    const start = this.createCompositeKey(objectType, attributes);
    const end = start + "\u{10ffff}";
    const matches = [...this.data.keys()]
      .filter((key) => key >= start && key < end)
      .sort()
      .map((key) => ({ value: this.data.get(key) ?? Buffer.alloc(0) }));
    let index = 0;
    return {
      next: async () => {
        if (index >= matches.length) {
          return { done: true };
        }
        const value = matches[index];
        index += 1;
        return { done: false, value };
      },
      close: async () => undefined,
    };
  }

  setEvent(name: string, payload: Uint8Array): void {
    if (name === "") {
      throw new Error("event name is empty");
    }
    this.events.push({ name, payload: Buffer.from(payload) });
  }
}

export interface Caller {
  role: string | null;
  agent: string | null;
  mspId: string;
  id: string;
}

export const PIPELINE_AGENT: Caller = {
  role: "pipeline-agent",
  agent: "ingestion",
  mspId: "Org1MSP",
  id: "x509::/CN=agent-ingestion/OU=client::/CN=ca.org1.example.com",
};

export class MemoryIdentity {
  constructor(private readonly caller: Caller) {}

  getAttributeValue(name: string): string | null {
    if (name === "role") {
      return this.caller.role;
    }
    if (name === "agent") {
      return this.caller.agent;
    }
    return null;
  }

  getMSPID(): string {
    return this.caller.mspId;
  }

  getID(): string {
    return this.caller.id;
  }
}

export function context(caller: Caller = PIPELINE_AGENT): { ctx: Context; stub: MemoryStub } {
  const stub = new MemoryStub();
  const ctx = { stub, clientIdentity: new MemoryIdentity(caller) } as unknown as Context;
  return { ctx, stub };
}
