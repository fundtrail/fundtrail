"""A small sample folder in the seed builder's layout, written for a test."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEDGER = "\n".join(
    [
        "line_id,transaction_date,posting_date,amount,description,account,vendor,reference,"
        "original_line_id",
        "L-9001-0001,2026-10-01,2026-10-05,120.00,Cable kit,55016 Lab Instruments and Supplies,"
        "Example Supply,INV-1,",
        "L-9001-0002,2026-11-20,2026-11-24,80.50,Probe tips,55016 Lab Instruments and Supplies,"
        "Example Supply,INV-2,",
        "L-9001-0003,2026-11-30,2026-12-07,45.00,Fittings,55016 Lab Instruments and Supplies,"
        "Example Hardware,R-3,",
        "",
    ]
)

FILES = {
    "award_letter.txt": b"Award SYN-9009001. Synthetic award letter.",
    "invoice_INV-1.txt": b"Invoice INV-1, $120.00",
    "invoice_INV-2.txt": b"Invoice INV-2, $80.50",
    "receipt_R-3.txt": b"Receipt R-3, $45.00",
    "email_INV-4.eml": (
        b"From: pi@university.example\r\n"
        b"To: grant@fundtrail.example\r\n"
        b"Subject: Fwd: Invoice INV-4\r\n"
        b"Date: Thu, 19 Nov 2026 09:00:00 -0800\r\n"
        b"Message-ID: <fwd-inv-4@university.example>\r\n"
        b"\r\n"
        b"Invoice INV-4, $12.00\r\n"
    ),
}

EVENTS: list[dict[str, Any]] = [
    {"at": "2026-11-16T17:30:00Z", "kind": "file", "file": "award_letter.txt", "source": "upload"},
    {"at": "2026-11-16T17:45:00Z", "kind": "ledger", "file": "ledger.csv"},
    {"at": "2026-11-16T17:50:00Z", "kind": "file", "file": "invoice_INV-1.txt", "source": "drive"},
    {
        "at": "2026-11-16T17:50:00Z",
        "kind": "file",
        "file": "invoice_INV-2.txt",
        "source": "gmail",
        "sender": "pi@university.example",
    },
    {
        "at": "2026-11-18T17:00:00Z",
        "kind": "file",
        "file": "receipt_R-3.txt",
        "source": "upload",
        "deliver": "user",
    },
    {
        "at": "2026-11-19T17:00:00Z",
        "kind": "file",
        "file": "email_INV-4.eml",
        "source": "gmail",
        "sender": "pi@university.example",
        "deliver": "user",
    },
]

ACTIONS = [
    {"at": "2026-11-16T17:40:00Z", "action": "confirm_terms", "file": "award_letter.txt"},
    {"at": "2026-11-18T17:00:00Z", "action": "deliver_file", "file": "receipt_R-3.txt"},
]


def write_pack(
    folder: Path,
    *,
    events: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    starts_at: str = "2026-11-16T17:30:00Z",
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ledger.csv").write_text(LEDGER)
    for name, data in FILES.items():
        (folder / name).write_bytes(data)
    timeline = {
        "sample": "test-sample",
        "starts_at": starts_at,
        "events": EVENTS if events is None else events,
    }
    (folder / "timeline.json").write_text(json.dumps(timeline))
    (folder / "user_actions.json").write_text(
        json.dumps({"sample": "test-sample", "actions": ACTIONS if actions is None else actions})
    )
    (folder / "sample.json").write_text(json.dumps({"award_number": "SYN-9009001"}))
    return folder
