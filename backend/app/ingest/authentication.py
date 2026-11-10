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

Parts of the header come from the sender, such as the envelope sender's name, which
may be a quoted string holding `;`, `(` or `=`. So the header is tokenized first:
every quoted string becomes a placeholder and every comment is removed, before any
`;` or property is read. A quote inside a comment is treated as a quoted string too,
because Gmail copies the envelope sender into its SPF comment.
"""

import re

GMAIL_AUTHSERV_ID = "mx.google.com"

_QUOTED = "QUOTED"  # what a quoted string becomes; it holds no `;`, `=`, `(` or `@`
_METHODS = {"dmarc", "dkim", "spf"}
_SPACES_AROUND_EQUALS = re.compile(r"\s*=\s*")


def _tokenize(value: str) -> str:
    """The header with quoted strings replaced by a placeholder and comments removed."""
    out: list[str] = []
    depth = 0  # comment nesting
    in_quote = False
    i = 0
    while i < len(value):
        ch = value[i]
        if in_quote:
            if ch == "\\":
                i += 1  # the escaped character is part of the quoted string
            elif ch == '"':
                in_quote = False
        elif ch == '"':
            in_quote = True
            if depth == 0:
                out.append(_QUOTED)
        elif ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0:
                out.append(" ")
        elif depth:
            if ch == "\\":
                i += 1
        else:
            out.append(ch)
        i += 1
    if in_quote or depth:
        return ""  # unbalanced: not trusted
    return "".join(out)


def _domain(value: str) -> str:
    return value.rsplit("@", 1)[-1].strip().lower().rstrip(".") if "@" in value else ""


def _results(header: str) -> tuple[str, list[tuple[str, str, dict[str, str]]]]:
    """The authserv-id, and each result as (method, result, {property: value})."""
    parts = _tokenize(header).split(";")
    head = parts[0].split()
    serv_id = head[0].lower() if head else ""
    results = []
    for part in parts[1:]:
        tokens = _SPACES_AROUND_EQUALS.sub("=", part).split()
        if not tokens or "=" not in tokens[0]:
            continue
        method, _, result = tokens[0].partition("=")
        props: dict[str, str] = {}
        for token in tokens[1:]:
            name, eq, prop_value = token.partition("=")
            if eq:
                props[name.lower()] = prop_value
        results.append((method.lower(), result.lower(), props))
    return serv_id, results


def is_verified(
    headers: dict[str, list[str]], sender: str | None, authserv_id: str = GMAIL_AUTHSERV_ID
) -> bool:
    """True when the mailbox's own authentication result passes for the sender's domain."""
    found = headers.get("authentication-results", [])
    if not sender or sender.count("@") != 1 or not found:
        return False
    serv_id, results = _results(" ".join(found[0].split()))
    if serv_id != authserv_id.lower():
        return False
    domain = _domain(sender)
    for method, result, props in results:
        if method not in _METHODS or result != "pass":
            continue
        if method == "dmarc" and props.get("header.from", "").lower().rstrip(".") == domain:
            return True
        if method == "dkim" and domain in (
            props.get("header.d", "").lower().rstrip("."),
            _domain(props.get("header.i", "")),
        ):
            return True
        if method == "spf" and _domain(props.get("smtp.mailfrom", "")) == domain:
            return True
    return False
