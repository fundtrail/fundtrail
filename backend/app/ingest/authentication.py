"""Whether a message really comes from the address in its From line.

The mailbox checks each message as it's delivered and records the result in an
`Authentication-Results` header (RFC 8601). This module reads that result; it
doesn't check SPF (Sender Policy Framework), DKIM (DomainKeys Identified Mail) or
DMARC (Domain-based Message Authentication, Reporting and Conformance) itself.

Only the topmost `Authentication-Results` header is read, and only when it was
written by the mailbox's own mail server (Gmail's is `mx.google.com`). The receiving
server adds its header above everything the sender wrote, so a header the sender
forged sits lower down and is never read.

A message is verified for its sender when one of these passes for the sender's domain:
- DMARC, with `header.from` the sender's domain
- DKIM, signed by the sender's domain (`header.d`, or the domain of `header.i`)
- SPF, with the envelope sender (`smtp.mailfrom`) at the sender's domain
"""

import re

GMAIL_AUTHSERV_ID = "mx.google.com"

_RESULT = re.compile(r"\b(dmarc|dkim|spf)\s*=\s*(\w+)([^;]*)", re.IGNORECASE)
_PROPERTY = re.compile(r"\b(header\.from|header\.d|header\.i|smtp\.mailfrom)\s*=\s*([^\s;()]+)")
_COMMENT = re.compile(r"\([^()]*\)")


def _domain(value: str) -> str:
    return value.rsplit("@", 1)[-1].strip().strip('"').lower().rstrip(".")


def is_verified(
    headers: dict[str, list[str]], sender: str | None, authserv_id: str = GMAIL_AUTHSERV_ID
) -> bool:
    """True when the mailbox's own authentication result passes for the sender's domain."""
    results = headers.get("authentication-results", [])
    if not sender or "@" not in sender or not results:
        return False
    top = _COMMENT.sub(" ", " ".join(results[0].split()))
    serv_id = top.split(";", 1)[0].strip().split()[0].lower() if top.strip() else ""
    if serv_id != authserv_id.lower():
        return False
    domain = _domain(sender)
    for method, result, rest in _RESULT.findall(top):
        if result.lower() != "pass":
            continue
        props = {k.lower(): _domain(v) for k, v in _PROPERTY.findall(rest)}
        method = method.lower()
        if method == "dmarc" and props.get("header.from") == domain:
            return True
        if method == "dkim" and domain in (props.get("header.d"), props.get("header.i")):
            return True
        if method == "spf" and props.get("smtp.mailfrom") == domain:
            return True
    return False
