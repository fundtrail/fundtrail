from app.ingest.addresses import TAG_LENGTH, find_tag, grant_address, new_tag, tag_of

MAILBOX = "fundtrail.demo@mail.example"
# Treat the synthetic domain as one that ignores dots, the way Gmail treats gmail.com.
DOTLESS = frozenset({"mail.example"})


def test_new_tags_are_short_random_codes() -> None:
    tags = {new_tag() for _ in range(200)}
    assert len(tags) == 200
    assert all(len(t) == TAG_LENGTH and t.isalnum() and t.islower() for t in tags)


def test_grant_address_is_mailbox_plus_tag() -> None:
    assert grant_address(MAILBOX, "abc23def") == "fundtrail.demo+abc23def@mail.example"


def test_tag_of() -> None:
    assert tag_of("fundtrail.demo+abc23def@mail.example", MAILBOX) == "abc23def"
    assert tag_of("FundTrail.Demo+ABC23DEF@Mail.example", MAILBOX) == "abc23def"  # case
    assert tag_of("fundtrail.demo@mail.example", MAILBOX) is None  # no tag
    assert tag_of("someone+abc23def@mail.example", MAILBOX) is None
    assert tag_of("fundtrail.demo+abc23def@other.example", MAILBOX) is None


def test_dots_are_ignored_only_for_the_domains_given() -> None:
    assert tag_of("fundtraildemo+abc23def@mail.example", MAILBOX) is None
    assert tag_of("fundtraildemo+abc23def@mail.example", MAILBOX, DOTLESS) == "abc23def"


def test_only_the_top_delivered_to_is_read() -> None:
    headers = {
        "delivered-to": [
            "fundtrail.demo+bcctag23@mail.example",
            "fundtrail.demo+abc23def@mail.example",  # lower: could be written by the sender
        ],
        "to": ["Lab <fundtrail.demo+abc23def@mail.example>"],
    }
    assert find_tag(headers, MAILBOX) == "bcctag23"


def test_to_and_cc_are_not_read_when_delivered_to_has_no_tag() -> None:
    headers = {
        "delivered-to": ["fundtrail.demo@mail.example"],
        "to": ["fundtrail.demo+abc23def@mail.example"],
    }
    assert find_tag(headers, MAILBOX) is None


def test_falls_back_to_to_and_cc_only_without_delivered_to() -> None:
    headers = {"to": ["a@x.example"], "cc": ["Box <fundtrail.demo+abc23def@mail.example>"]}
    assert find_tag(headers, MAILBOX) == "abc23def"
    assert find_tag({"to": ["fundtrail.demo@mail.example"]}, MAILBOX) is None
