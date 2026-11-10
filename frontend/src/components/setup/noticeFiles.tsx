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
 * on the grant was read from, named as the evidence list names it.
 */
export function noticeFilesFrom(terms: TermView[], cards: EvidenceCard[]): NoticeFile[] {
  const cited = new Set(terms.filter((t) => isTermKind(t.record.data.kind)).flatMap((t) => citedFileIds(t.record)));
  return cards
    .filter((c) => cited.has(c.file.id))
    .sort((a, b) => a.file.arrived_at.localeCompare(b.file.arrived_at))
    .map((c) => ({ id: c.file.id, name: c.file.name }));
}

const NoticeFilesContext = createContext<NoticeFile[]>([]);

export function NoticeFilesProvider({ files, children }: { files: NoticeFile[]; children: ReactNode }) {
  return <NoticeFilesContext.Provider value={files}>{children}</NoticeFilesContext.Provider>;
}

export function useNoticeFiles(): NoticeFile[] {
  return useContext(NoticeFilesContext);
}
