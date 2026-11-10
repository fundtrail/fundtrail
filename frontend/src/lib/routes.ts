// Every page the screens link to, in one place, so a screen never spells a path
// out. Some of these pages are built by other screens' builders and may not
// exist yet; a link to one is still right.

import type { Id } from "./api/types";

const e = encodeURIComponent;

/** Where the viewer opens a file: one record, and optionally one of its values. */
export interface ViewerSpot {
  recordId: Id;
  value?: string;
}

export const routes = {
  signIn: () => "/sign-in",
  home: () => "/",

  // A workspace
  workspace: (workspaceId: Id) => `/w/${e(workspaceId)}`,
  newGrant: (workspaceId: Id) => `/w/${e(workspaceId)}/grants/new`,
  mail: (workspaceId: Id) => `/w/${e(workspaceId)}/mail`,

  // A grant
  grant: (grantId: Id) => `/grants/${e(grantId)}`,
  terms: (grantId: Id) => `/grants/${e(grantId)}/terms`,
  /** The reusable notes, a section of the terms page. */
  reusableNotes: (grantId: Id) => `/grants/${e(grantId)}/terms#reusable-notes`,
  ledger: (grantId: Id) => `/grants/${e(grantId)}/ledger`,
  closeout: (grantId: Id) => `/grants/${e(grantId)}/closeout`,

  /** Every file on the grant: the evidence cards. */
  evidence: (grantId: Id) => `/grants/${e(grantId)}/files`,

  // One item on a grant
  charge: (grantId: Id, chargeId: Id) => `/grants/${e(grantId)}/charges/${e(chargeId)}`,
  record: (grantId: Id, recordId: Id) => `/grants/${e(grantId)}/records/${e(recordId)}`,
  /**
   * One file in the viewer. With `at`, it opens at one value of one record:
   * `value` names it the server's way ("total", "items[0].amount"), or "part"
   * for a link's part. An answer's quotes aren't supported by the viewer yet.
   */
  file: (grantId: Id, fileId: Id, at?: ViewerSpot) => {
    const base = `/grants/${e(grantId)}/files/${e(fileId)}`;
    if (!at) return base;
    const query = new URLSearchParams({ record: at.recordId });
    if (at.value) query.set("value", at.value);
    return `${base}?${query.toString()}`;
  },
  /** Confirming or typing the values of one record that couldn't be found in its file. */
  confirmValues: (grantId: Id, fileId: Id, recordId: Id) =>
    `/grants/${e(grantId)}/files/${e(fileId)}/confirm?${new URLSearchParams({ record: recordId }).toString()}`,
} as const;
