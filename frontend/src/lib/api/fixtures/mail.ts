// Mail held for the sample grant (decision 0025). Owned by the mail screen's
// builder.
//
// The sample grant itself holds no mail, so this adds one synthetic message
// from a sender nobody added: a vendor sending a copy of invoice INV-1001
// straight to the grant's address. The grant's problem list shows it too.

import type { ApiClient } from "../client";
import type { HeldMail } from "../types";
import { served, SAMPLE_GRANT_ID, WORKSPACE_ID } from "./sample";

export const SAMPLE_HELD_MAIL: HeldMail[] = [
  {
    id: "held-inv-1001-copy",
    workspace_id: WORKSPACE_ID,
    grant_id: SAMPLE_GRANT_ID,
    sender: "billing@labsupply.example",
    reason: "unknown_sender",
    source_ref: "gmail-synthetic-0002",
    subject: "Invoice INV-1001",
    held_at: "2026-04-08T14:10:00Z",
    files: [
      {
        name: "message.eml",
        media_type: "message/rfc822",
        storage_path: `${WORKSPACE_ID}/${SAMPLE_GRANT_ID}/held-inv-1001-copy/message.eml`,
        sha256: "fake-held-inv-1001-copy-message",
      },
      {
        name: "INV-1001.pdf",
        media_type: "application/pdf",
        storage_path: `${WORKSPACE_ID}/${SAMPLE_GRANT_ID}/held-inv-1001-copy/INV-1001.pdf`,
        sha256: "fake-held-inv-1001-copy-attachment",
      },
    ],
  },
];

export function mailFake(): Pick<ApiClient, "listHeldMail"> {
  return { listHeldMail: (workspaceId) => served(workspaceId === WORKSPACE_ID ? SAMPLE_HELD_MAIL : undefined) };
}
