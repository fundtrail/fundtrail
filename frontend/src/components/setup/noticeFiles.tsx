"use client";

// The grant's notice files: the documents its terms were read from, the award
// letter and its amendments. A budget line the accountant types names one of
// them (issue 104, product call 42). First version, may change.

import { createContext, useContext, type ReactNode } from "react";
import type { EvidenceCard, FtRecord, Id, TermView } from "@/lib/api";
import { isTermKind } from "./termFields";

export interface NoticeFile {
  id: Id;
  name: string;
}

/** Whether the evidence list the notice files come from has loaded. */
export type NoticeFilesStatus = "loading" | "error" | "ready";

export interface NoticeFiles {
  status: NoticeFilesStatus;
  /** The files offered as notices. */
  files: NoticeFile[];
  /** Every file on the grant by ID, to name a saved notice that's no longer offered. */
  names: Record<Id, string>;
}

/** The files the record's values are cited in, first one first. */
export function citedFileIds(record: FtRecord): Id[] {
  const ids: Id[] = [];
  for (const value of Object.values(record.data)) {
    const fileId = (value as { citation?: { file_id?: Id } | null } | null)?.citation?.file_id;
    if (fileId && !ids.includes(fileId)) ids.push(fileId);
  }
  return ids;
}

/**
 * The grant's notice files, in the order the files arrived: every file a term
 * on the grant was read from, named as the evidence list names it. A file
 * whose only terms were rejected isn't offered.
 */
export function noticeFilesFrom(terms: TermView[], cards: EvidenceCard[]): NoticeFile[] {
  const cited = new Set(
    terms.filter((t) => isTermKind(t.record.data.kind) && t.state !== "rejected").flatMap((t) => citedFileIds(t.record)),
  );
  return cards
    .filter((c) => cited.has(c.file.id))
    .sort((a, b) => a.file.arrived_at.localeCompare(b.file.arrived_at))
    .map((c) => ({ id: c.file.id, name: c.file.name }));
}

/** What the terms page hands the term cards, from the grant's terms and its evidence list as it loads. */
export function noticeFilesFor(terms: TermView[], evidence: { data?: EvidenceCard[]; error?: unknown }): NoticeFiles {
  if (evidence.data) {
    return {
      status: "ready",
      files: noticeFilesFrom(terms, evidence.data),
      names: Object.fromEntries(evidence.data.map((c) => [c.file.id, c.file.name])),
    };
  }
  return { status: evidence.error ? "error" : "loading", files: [], names: {} };
}

const NoticeFilesContext = createContext<NoticeFiles>({ status: "ready", files: [], names: {} });

export function NoticeFilesProvider({ value, children }: { value: NoticeFiles; children: ReactNode }) {
  return <NoticeFilesContext.Provider value={value}>{children}</NoticeFilesContext.Provider>;
}

export function useNoticeFiles(): NoticeFiles {
  return useContext(NoticeFilesContext);
}
