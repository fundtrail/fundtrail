import type { Id } from "@/lib/api";
import { routes } from "@/lib/routes";

/**
 * The grant's evidence cards. routes.ts doesn't name this page yet, so it's
 * built from the grant's path until it does.
 */
export function evidenceHref(grantId: Id): string {
  return `${routes.grant(grantId)}/files`;
}

/**
 * The viewer for a file, opened at one value of one record when both are given.
 * `path` names the value the server's way ("total", "items[0].amount"), or a
 * link's "part".
 */
export function viewerHref(grantId: Id, fileId: Id, recordId?: Id, path?: string): string {
  const base = routes.file(grantId, fileId);
  if (!recordId) return base;
  const q = new URLSearchParams({ record: recordId });
  if (path) q.set("value", path);
  return `${base}?${q.toString()}`;
}

/** The screen for confirming or typing the values of one record that couldn't be found. */
export function confirmHref(grantId: Id, fileId: Id, recordId: Id): string {
  return `${routes.file(grantId, fileId)}/confirm?${new URLSearchParams({ record: recordId }).toString()}`;
}
