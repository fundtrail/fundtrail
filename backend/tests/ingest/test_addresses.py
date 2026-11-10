from app.ingest.addresses import TAG_LENGTH, find_tag, grant_address, new_tag, tag_of

MAILBOX = "fundtrail.demo@gmail.com"


def test_new_tags_are_short_random_codes() -> None:
    tags = {new_tag() for _ in range(200)}
    assert len(tags) == 200
    assert all(len(t) == TAG_LENGTH and t.isalnum() and t.islower() for t in tags)


def test_grant_address_is_mailbox_plus_tag() -> None:
    assert grant_address(MAILBOX, "abc23def") == "fundtrail.demo+abc23def@gmail.com"


def test_tag_of() -> None:
    assert tag_of("fundtrail.demo+abc23def@gmail.com", MAILBOX) == "abc23def"
    assert tag_of("FundTrailDemo+ABC23DEF@Gmail.com", MAILBOX) == "abc23def"  # dots, case
    assert tag_of("fundtrail.demo@gmail.com", MAILBOX) is None  # no tag
    assert tag_of("someone+abc23def@gmail.com", MAILBOX) is None
    assert tag_of("fundtrail.demo+abc23def@other.example", MAILBOX) is None


def test_delivered_to_is_read_first() -> None:
    headers = {
        "delivered-to": ["fundtrail.demo+bcc0tag2@gmail.com"],
        "to": ["Lab <fundtrail.demo+abc23def@gmail.com>"],
    }
    assert find_tag(headers, MAILBOX) == "bcc0tag2"


def test_falls_back_to_to_and_cc() -> None:
    headers = {"to": ["a@x.example"], "cc": ["Box <fundtrail.demo+abc23def@gmail.com>"]}
    assert find_tag(headers, MAILBOX) == "abc23def"
    assert find_tag({"to": ["fundtrail.demo@gmail.com"]}, MAILBOX) is None
