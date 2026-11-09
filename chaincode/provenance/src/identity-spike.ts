import { Context, Contract, Info, Transaction } from "fabric-contract-api";

interface AttributeRecord {
  role: string;
  agent: string;
  mspId: string;
}

@Info({
  title: "IdentitySpike",
  description: "Reads role and agent from the caller certificate",
})
export class IdentitySpike extends Contract {
  @Transaction()
  public async Write(ctx: Context, key: string): Promise<string> {
    const role = ctx.clientIdentity.getAttributeValue("role");
    const agent = ctx.clientIdentity.getAttributeValue("agent");
    if (role !== "pipeline-agent" || agent === null || agent === "") {
      throw new Error("FORBIDDEN");
    }
    const record: AttributeRecord = {
      role,
      agent,
      mspId: ctx.clientIdentity.getMSPID(),
    };
    const payload = JSON.stringify(record);
    await ctx.stub.putState(key, Buffer.from(payload));
    return payload;
  }

  @Transaction(false)
  public async Read(ctx: Context, key: string): Promise<string> {
    const stored = await ctx.stub.getState(key);
    if (stored.length === 0) {
      throw new Error("NOT_FOUND");
    }
    return Buffer.from(stored).toString("utf8");
  }
}
