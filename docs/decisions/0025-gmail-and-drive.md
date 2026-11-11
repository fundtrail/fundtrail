# 0025. Gmail and Drive bring files in through one account the app owns

**Date:** 2026-11-10 · **Status:** accepted for a user's own grants. Reviewed by Alex on 2026-11-10 and kept as written: an address per grant made of the app's mailbox and a random code, known senders are the people named in the award letter, anyone the accountant adds and the workspace's members who can act, mail from anyone else is held with three actions, a forwarded approval counts only if its original sender is known, and a Drive folder is tied by its link, with Google files exported to Portable Document Format (PDF). Builds on [0013](0013-stack-additions-and-repo-structure.md). Amended by [0027](0027-sample-grants.md) and [0028](0028-one-clock-per-grant.md) (Gmail and Drive work on a sample grant as on any grant, and a live email there is dated to the simulated time) and [0029](0029-workspace-members-and-one-access-check.md) (known senders include the addresses of the workspace's members who can act, not only the accountant's).

## Context

Evidence reaches a grant three ways: an upload in the app, an email to the grant's address, and a file in a Drive folder. The docs settle the outline: one Google account that the app owns, checked on a timer, users never connecting their own Google account, and only email from known senders being read ([architecture.md](../architecture.md#evidence-why-the-spending-was-allowed)). They leave open the address, how a folder is tied to a grant, what happens to held mail, and what an email becomes.

Three facts from Google's own documentation shape the answer.

- Mail sent to an address with a plus sign and a tag arrives in the plain address's inbox.
- The permissions needed to read mail and to read shared Drive files are ones Google calls restricted. Google requires a security assessment of an app that stores data from them on its servers. While a Google project is in testing, its sign-in expires every seven days.
- A Google Doc has no original file. It can only be exported.

And one rule of ours gets in the way: demo data uses `.example` addresses, which can't send or receive real mail.

## Decision

- **Upload is the way in that always works.** Gmail and Drive are conveniences on top of it, and nothing in the app depends on them.
- **Each grant's address is the app's mailbox with a tag:** the mailbox name, a plus sign, and a short random code for that grant. The code isn't the award number, so the address can't be guessed. Code sends each message to its grant by the address it was delivered to. Mail with no tag, or an unknown one, is ignored. Whether the tag always survives, and how the delivered-to address is best read, is checked when it's built: some senders' mail systems drop the tag.
- **Known senders** are the people named in the award letter who have an email address, once that term is confirmed, anyone the accountant adds, and the accountant's own sign-in address, so they can forward things. Confirming a person's term lets in the mail already held from them, the same as adding them.
- **Mail from anyone else is held.** It's stored, the agent doesn't read it, and no check uses it. The grant's problem list shows that mail is held and from whom. The accountant can let one message in, add the sender as known, which lets in everything held from them, or dismiss it. A dismissed message stays stored and unread. A message that's let in arrives at that moment.
- **A forwarded message** from a known sender is read. The agent finds the original sender in it, with a citation, and code decides an approver's role from that address ([architecture.md](../architecture.md#trust-rules)). An approval whose original sender nobody knows can't count as an approval, so the charge it was offered for goes to Needs a human. An invoice forwarded the same way is still an invoice.
- **An email becomes one file per thing in it.** The message itself is one evidence file, kept as it arrived. Each attached document is its own evidence file that points back to the message, and so is each attachment of a message that was forwarded as an attachment. Only very small images, such as a logo or a signature mark, are skipped. A photo pasted into the body of a message is kept.
- **That makes the duplicate check work across channels.** An invoice attached to an email and the same invoice uploaded are the exact same file, so code catches it. Copies that differ go through the likely-duplicate steps already decided ([0010](0010-agent-suggests-accountant-decides.md)).
- **A Drive folder is tied to a grant by its link.** The accountant shares a folder with the app's account and pastes the folder's link on the grant. The app reads that folder and the folders inside it. A new file becomes an evidence file. A file that Drive says was modified arrives as a new evidence file, and the earlier one stays. A file that's still being edited is taken in once it has stopped changing for a while, so a document being written doesn't arrive again at every check.
- **A Google Doc, Sheet or Slides file is exported to a Portable Document Format (PDF) file** when it's read, and the export is what's stored. Its evidence card says it's an export.
- **Seeded email never goes through Gmail.** The demo's `.example` messages are files in the seed. Live Gmail is for real addresses, starting with the accountant's own. The people named in a seeded award letter will never match live mail, and that's expected.
- **Building and testing need no Google account.** Mail and Drive sit behind one small interface, with a stand-in that reads message files and folders from disk. The real services are used only in the smoke test.

## Considered and set aside

- **An address on our own domain.** It looks better and avoids the plus sign, but it needs a domain and paid mail. Later.
- **One shared address, with the agent choosing the grant.** A wrong guess files evidence on the wrong grant.
- **Users connecting their own Google account** to pick a folder. It avoids the restricted permission, but the docs rule it out for now.
- **Reading mail from anyone.** Anyone could then put evidence on a grant.
- **Keeping only the attachments.** An approval is often the text of the message itself.

## Consequences

- The contracts add held mail and its three actions, a grant's address and its Drive folder. Names, fields and routes are open.
- The app's Google sign-in expires weekly while the Google project is in testing. Whether publishing the project removes that for a single account the app owns has to be checked against Google's current rules before anyone relies on it.
- Serving outside users means Google's assessment of how the app stores what it reads through the restricted permissions.
- A vendor who emails an invoice straight to the grant's address is held until the accountant adds them.
- Whether a file added inside a shared folder always appears, and how folders inside folders are read, are checked when it's built.

## For review

The calls most likely to change: the plus-sign address, holding mail from vendors, and exporting Google Docs to PDF.
