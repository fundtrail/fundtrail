// Names the change one of the agent's waiting records would make, so a
// suggestion can say what accepting it does. Plain wording per record kind;
// the bucket and the reasons stay the server's.

import type { ChecklistEntry, EvidenceFile, FtRecord, Id } from "@/lib/api";
import { money, recordKindLabel } from "@/lib/format";
import { ANSWER_LABELS, citedValue, field, recordName } from "../charge/labels";

export interface Change {
  /** What accepting does, in one line. */
  title: string;
  /** What's in force now, when the suggestion replaces something. */
  now?: string;
  /** What the agent suggests instead. */
  suggested?: string;
  /** The agent's own reason or reasoning, labeled as the agent's where shown. */
  reason?: string;
}

export interface DescribeContext {
  records: Record<Id, FtRecord>;
  files: Record<Id, EvidenceFile>;
  checklist: ChecklistEntry[];
}

function summary(record: FtRecord, ctx: DescribeContext): string {
  switch (record.data.kind) {
    case "judgment": {
      const answer = field<string>(record, "answer") ?? "";
      return ANSWER_LABELS[answer] ?? answer;
    }
    case "link": {
      const target = ctx.records[field<string>(record, "record_id") ?? ""];
      const amount = field<number | null>(record, "amount_cents");
      const name = target ? recordName(target, ctx.files) : "a record";
      return amount === null || amount === undefined ? name : `${name}, ${money(amount)}`;
    }
    case "budget_assignment": {
      const line = ctx.records[field<string>(record, "record_id") ?? ""];
      return citedValue<string>(line, "name") ?? "a budget line";
    }
    case "checklist_item":
      return field<string>(record, "needed") ?? "a checklist item";
    case "bill": {
      const total = citedValue<number>(record, "total");
      return total === undefined ? recordName(record, ctx.files) : `${recordName(record, ctx.files)}, ${money(total)}`;
    }
    default:
      return recordName(record, ctx.files);
  }
}

function itemNeeded(record: FtRecord, ctx: DescribeContext): string {
  const entry = ctx.checklist.find((e) => e.removal_waiting_id === record.id);
  if (entry) return entry.needed;
  const itemId = field<string | null>(record, "item_record_id");
  const item = itemId ? ctx.records[itemId] : undefined;
  return field<string>(item, "needed") ?? field<string>(record, "default_item") ?? "an item";
}

function reasonOf(record: FtRecord): string | undefined {
  return field<string | null>(record, "reason") ?? field<string | null>(record, "reasoning") ?? undefined;
}

/** What accepting one of the agent's waiting records changes. */
export function describeChange(record: FtRecord, replaces: FtRecord | null, ctx: DescribeContext): Change {
  const reason = reasonOf(record);
  const kind = record.data.kind;
  if (kind === "checklist_removal") {
    return { title: `Remove "${itemNeeded(record, ctx)}" from the checklist`, reason };
  }
  if (kind === "retraction") {
    const what = replaces ? recordKindLabel(replaces.data.kind).toLowerCase() : "a record";
    return { title: `Withdraw ${what}`, now: replaces ? summary(replaces, ctx) : undefined, reason };
  }
  if (kind === "duplicate") {
    const copy = ctx.files[field<string>(record, "copy_file_id") ?? ""];
    const original = ctx.files[field<string>(record, "original_file_id") ?? ""];
    return { title: `Mark ${copy?.name ?? "a file"} as a copy of ${original?.name ?? "another file"}`, reason };
  }
  if (replaces) {
    return {
      title: `Change ${recordKindLabel(kind).toLowerCase()}`,
      now: summary(replaces, ctx),
      suggested: summary(record, ctx),
      reason,
    };
  }
  return { title: `Add ${recordKindLabel(kind).toLowerCase()}`, suggested: summary(record, ctx), reason };
}
