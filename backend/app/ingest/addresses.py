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

_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def new_tag() -> str:
    """A short random code for a new grant. It isn't the award number, so it can't be guessed."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(TAG_LENGTH))


def grant_address(mailbox: str, tag: str) -> str:
    local, domain = mailbox.split("@", 1)
    return f"{local}+{tag}@{domain}"


def _local_key(local: str, domain: str) -> str:
    # Gmail ignores dots in the name part of its own addresses.
    return local.replace(".", "") if domain in _GMAIL_DOMAINS else local


def tag_of(address: str, mailbox: str) -> str | None:
    """The tag in `address` if it is the mailbox with a tag, else None."""
    address = address.strip().lower()
    if "@" not in address:
        return None
    local, domain = address.rsplit("@", 1)
    box_local, box_domain = mailbox.strip().lower().rsplit("@", 1)
    if domain != box_domain or "+" not in local:
        return None
    base, tag = local.split("+", 1)
    if _local_key(base, domain) != _local_key(box_local, box_domain) or not tag:
        return None
    return tag


def find_tag(headers: dict[str, list[str]], mailbox: str) -> str | None:
    """Read the tag from the delivered-to address.

    `headers` maps a lower-case header name to its values in order. Gmail stamps
    `Delivered-To` with the address a message was delivered to, which includes the
    tag even when the grant's address was only a Bcc. `X-Original-To`, `To` and `Cc`
    are read after it, for a message whose delivered-to address is missing.
    """
    for name in ("delivered-to", "x-original-to", "to", "cc"):
        for _, address in getaddresses(headers.get(name, [])):
            tag = tag_of(address, mailbox)
            if tag:
                return tag
    return None
