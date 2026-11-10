import { Context, Contract, Info, Transaction } from "fabric-contract-api";

import {
  type ArtifactRecord,
  type CallerIdentity,
  certificateSubject,
  parseClientArtifact,
  requirePipelineAgent,
  requireUuid,
} from "./artifact";
import { fail } from "./errors";

function callerOf(ctx: Context): CallerIdentity {
  return {
    mspId: ctx.clientIdentity.getMSPID(),
    subject: certificateSubject(ctx.clientIdentity.getID()),
    role: ctx.clientIdentity.getAttributeValue("role"),
    agent: ctx.clientIdentity.getAttributeValue("agent"),
  };
}

@Info({
  title: "Provenance",
  description: "Creates and reads closed-schema ARTIFACT records",
})
export class Provenance extends Contract {
  @Transaction()
  public async CreateArtifactRecord(ctx: Context, json: string): Promise<string> {
    // Who may write comes first: a caller without the role learns nothing about the schema.
    const caller = callerOf(ctx);
    const creatorAgent = requirePipelineAgent(caller);
    const client = parseClientArtifact(json);
    const existing = await ctx.stub.getState(client.artifactId);
    if (existing.length !== 0) {
      fail("DUPLICATE", "artifactId already exists");
    }
    const record: ArtifactRecord = {
      docType: "artifact",
      ...client,
      txTimestamp: ctx.stub.getDateTimestamp().toISOString(),
      creatorMspId: caller.mspId,
      creatorId: caller.subject,
      creatorAgent,
    };
    const payload = JSON.stringify(record);
    await ctx.stub.putState(client.artifactId, Buffer.from(payload));
    return payload;
  }

  @Transaction(false)
  public async GetArtifactRecord(ctx: Context, artifactId: string): Promise<string> {
    requireUuid(artifactId, "artifactId");
    const stored = await ctx.stub.getState(artifactId);
    if (stored.length === 0) {
      fail("NOT_FOUND", "artifactId is not on the ledger");
    }
    return Buffer.from(stored).toString("utf8");
  }
}
