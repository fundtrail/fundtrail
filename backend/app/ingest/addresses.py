"""Each grant's address, and sending a message to its grant by the address it was delivered to.

A grant's address is the app's mailbox name, a plus sign and a short random code
(decision 0025). Gmail delivers `name+tag@domain` to `name@domain`'s inbox
(https://support.google.com/mail/answer/12096). Mail with no tag, or a tag no grant
has, is ignored.
"""

import secrets
from email.utils import getaddresses

# No 0/o, 1/l/i: the code is read aloud and typed by hand.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TAG_LENGTH = 8

# Domains whose mail system ignores dots in the name part of an address. Gmail does for
# its own addresses.
GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def new_tag() -> str:
    """A short random code for a new grant. It isn't the award number, so it can't be guessed."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(TAG_LENGTH))


def grant_address(mailbox: str, tag: str) -> str:
    local, domain = mailbox.split("@", 1)
    return f"{local}+{tag}@{domain}"


def tag_of(
    address: str, mailbox: str, dotless_domains: frozenset[str] = GMAIL_DOMAINS
) -> str | None:
    """The tag in `address` if it is the mailbox with a tag, else None."""
    address = address.strip().lower()
    if address.count("@") != 1:
        return None
    local, domain = address.split("@")
    box_local, box_domain = mailbox.strip().lower().rsplit("@", 1)
    if domain != box_domain or "+" not in local:
        return None
    base, tag = local.split("+", 1)

    def key(name: str) -> str:
        return name.replace(".", "") if domain in dotless_domains else name

    if key(base) != key(box_local) or not tag:
        return None
    return tag


def find_tag(
    headers: dict[str, list[str]], mailbox: str, dotless_domains: frozenset[str] = GMAIL_DOMAINS
) -> str | None:
    """Read the tag from the address the message was delivered to.

    `headers` maps a lower-case header name to its values, top first. The receiving
    mail server adds `Delivered-To` above everything the sender wrote, so only the top
    one is read: lower ones, like `To` and `Cc`, can be written by the sender, who could
    then choose the grant. Only a message with no `Delivered-To` at all falls back to the
    top `X-Original-To`, then to `To` and `Cc`, which the disk stand-in and some other
    mail systems need.
    """
    if "delivered-to" in headers:
        candidates = headers["delivered-to"][:1]
    elif "x-original-to" in headers:
        candidates = headers["x-original-to"][:1]
    else:
        candidates = headers.get("to", []) + headers.get("cc", [])
    for _, address in getaddresses(candidates):
        tag = tag_of(address, mailbox, dotless_domains)
        if tag:
            return tag
    return None
