// Every page the screens link to, in one place, so a screen never spells a path
// out. Some of these pages are built by other screens' builders and may not
// exist yet; a link to one is still right.

import type { Id } from "./api/types";

const e = encodeURIComponent;

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

  // One item on a grant
  charge: (grantId: Id, chargeId: Id) => `/grants/${e(grantId)}/charges/${e(chargeId)}`,
  record: (grantId: Id, recordId: Id) => `/grants/${e(grantId)}/records/${e(recordId)}`,
  file: (grantId: Id, fileId: Id) => `/grants/${e(grantId)}/files/${e(fileId)}`,
} as const;
