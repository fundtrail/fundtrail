# 0029. A workspace has members, and one place decides who may reach what

**Date:** 2026-11-10 · **Status:** accepted. Builds on [0007](0007-real-app-first.md).

## Context

The docs say the accountant is the only user and each workspace has one person, for now ([0007](0007-real-app-first.md), [product.md](../product.md#users-and-workspaces)). The product owner wants the design to stay flexible for more people later, without building that now.

Two scenarios show what would block it.

- **A second account in a one-person workspace.** When the user skips the human steps on a sample grant, the decisions belong to the workspace's sample accountant ([0027](0027-sample-grants.md)). If the code assumes the workspace's owner wrote every decision, the sample's history either breaks or gets credited to the user.
- **Access checked in many places.** Every route checks on its own that the user owns the workspace. When a second person joins, every one of those checks has to be found and changed, and the one that's missed lets the wrong person in or keeps the right one out.

## Decision

- **A membership list:** workspace, user and role. The owner and the workspace's sample accountant are members.
- **One place answers whether a user may reach a workspace or a grant,** and it's used everywhere.
- **Nothing may assume a workspace has one person.** The evidence report's preparer is whoever signs off. Known senders include the addresses of the members who can act.
- **A database rule:** a user-written record's author is a member of that record's workspace.
- **Not built and not decided:** invitations, roles on screen, and access to only some grants.

## Considered and set aside

- **The workspace's owner as the only access rule.** It's the assumption that breaks when a second person joins.
- **Building invitations and roles now.** The product owner wants room for them, not the feature.

## Consequences

- Until invitations are built, the owner is the only member who can sign in.
- [0022](0022-evidence-report-and-sign-off.md)'s "a workspace has one person for now" no longer holds. The preparer is whoever signs off.
- [0025](0025-gmail-and-drive.md)'s known senders change from "the accountant's own sign-in address" to the addresses of the members who can act.
- The contracts add the membership list and its roles, and the ownership check in the application programming interface (API) becomes the one access check. Names and fields are open ([contracts.md](../contracts.md#not-decided-yet)).
