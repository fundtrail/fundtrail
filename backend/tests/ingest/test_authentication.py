import pytest

from app.ingest.authentication import is_verified

from .mail_factory import PI, gmail_auth


def headers(*results: str) -> dict[str, list[str]]:
    return {"authentication-results": list(results)}


def test_pass_for_the_senders_domain() -> None:
    assert is_verified(headers(gmail_auth(PI, "pass")), PI)


def test_fail_or_missing_is_not_verified() -> None:
    assert not is_verified(headers(gmail_auth(PI, "fail")), PI)
    assert not is_verified({}, PI)
    assert not is_verified(headers(gmail_auth(PI, "pass")), None)


def test_a_pass_for_another_domain_does_not_count() -> None:
    other = gmail_auth("someone@elsewhere.example", "pass")
    assert not is_verified(headers(other), PI)


def test_only_the_mailboxs_own_topmost_result_is_read() -> None:
    forged = "mx.forged.example; dmarc=pass header.from=university.example"
    assert not is_verified(headers(forged), PI)
    assert not is_verified(headers(gmail_auth(PI, "fail"), gmail_auth(PI, "pass")), PI)


def test_any_one_aligned_method_is_enough() -> None:
    dkim_only = "mx.google.com; dkim=pass header.i=@university.example; spf=softfail"
    spf_only = f"mx.google.com; spf=pass (comment; with a semicolon) smtp.mailfrom={PI}"
    assert is_verified(headers(dkim_only), PI)
    assert is_verified(headers(f"mx.google.com; spf=pass smtp.mailfrom={PI}"), PI)
    assert not is_verified(headers(spf_only.replace("pass", "fail")), PI)


@pytest.mark.parametrize(
    "forged",
    [
        # A `;` inside a quoted envelope sender starts no new result.
        'mx.google.com; spf=softfail smtp.mailfrom="a;dmarc=pass '
        'header.from=university.example x"@bad.example',
        # A quoted string inside Gmail's own SPF comment doesn't end the comment.
        'mx.google.com; spf=softfail (google.com: domain of "a); dmarc=pass '
        'header.from=university.example ; (b"@bad.example does not designate 192.0.2.1) '
        'smtp.mailfrom="a); dmarc=pass header.from=university.example ; (b"@bad.example',
        # A quoted DKIM identity is read as its real domain.
        'mx.google.com; dkim=pass header.i="x;dmarc=pass '
        'header.from=university.example y"@bad.example',
    ],
)
def test_quoted_strings_cant_forge_a_result(forged: str) -> None:
    assert not is_verified(headers(forged), PI)


def test_unbalanced_quotes_or_comments_are_not_trusted() -> None:
    assert not is_verified(
        headers('mx.google.com; dmarc=pass header.from=university.example "'), PI
    )
    assert not is_verified(headers("mx.google.com; (dmarc=pass header.from=university.example"), PI)
    assert is_verified(
        headers(f'mx.google.com; spf=pass (domain of "q;x"@university.example) smtp.mailfrom={PI}'),
        PI,
    )
