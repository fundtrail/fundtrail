// Plain words for the charge page. Status text and reasons come from the server
// as they are; these only name things the bodies carry as codes.

import type { Author, Citation, EvidenceFile, FtRecord, Id } from "@/lib/api";
import { recordKindLabel } from "@/lib/format";

/** Who wrote something, as the thread and the page label it. */
export const AUTHOR_LABELS: Record<Author, string> = { agent: "Agent", user: "Accountant" };

/** Who added a checklist item. */
export const ADDED_BY_LABELS = {
  default: "Account default",
  agent: "Added by the agent",
  user: "Added by the accountant",
} as const;

/** The questions code asks, as product.md words them. */
export const QUESTION_LABELS: Record<string, string> = {
  allowable: "Is this cost necessary and reasonable, and is it for this project?",
  covers: "Does this approval cover this charge?",
  unusual_term: "Does this term change anything for this charge?",
  flag: "The agent's own question",
};

export const ANSWER_LABELS: Record<string, string> = {
  supports: "Supports",
  contradicts: "Contradicts",
  unsure: "Unsure",
};

/** A record's data field, read loosely: the screens carry most kinds as the server sends them. */
export function field<T = unknown>(record: FtRecord | null | undefined, name: string): T | undefined {
  if (!record) return undefined;
  return (record.data as unknown as Record<string, unknown>)[name] as T | undefined;
}

/** A cited value's value, or undefined. */
export function citedValue<T>(record: FtRecord | null | undefined, name: string): T | undefined {
  const value = field<{ value: T } | null>(record, name);
  return value ? value.value : undefined;
}

/** A short name for a record: its file, else its kind. */
export function recordName(record: FtRecord, files: Record<Id, EvidenceFile>): string {
  const fileId = citationFileId(record);
  const file = fileId ? files[fileId] : undefined;
  const kind = recordKindLabel(record.data.kind);
  return file ? `${kind}, ${file.name}` : kind;
}

/** The file a record was read from: the first citation in its data. */
export function citationFileId(record: FtRecord): Id | null {
  const found = findCitation(record.data);
  return found ? found.file_id : null;
}

function findCitation(value: unknown): Citation | null {
  if (!value || typeof value !== "object") return null;
  if (Array.isArray(value)) {
    for (const item of value) {
      const c = findCitation(item);
      if (c) return c;
    }
    return null;
  }
  const obj = value as Record<string, unknown>;
  if (typeof obj.file_id === "string" && "location" in obj) return obj as unknown as Citation;
  for (const key of Object.keys(obj)) {
    const c = findCitation(obj[key]);
    if (c) return c;
  }
  return null;
}
