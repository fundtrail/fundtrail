"""Fields to extract from each kind of document."""

from __future__ import annotations

from dataclasses import dataclass

from fundtrail.normalize import FieldKind


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: FieldKind
    description: str


AWARD_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("award_number", "text", "the award number"),
    FieldSpec("recipient", "text", "the recipient organization"),
    FieldSpec("principal_investigator", "text", "the principal investigator's name"),
    FieldSpec("period_start", "date", "the first day of the period of performance"),
    FieldSpec("period_end", "date", "the last day of the period of performance"),
    FieldSpec("total_direct_costs", "money", "the total amount awarded in direct costs"),
    FieldSpec("psc_budget", "money", "the amount budgeted for participant support costs"),
    FieldSpec(
        "psc_rebudget_approver",
        "text",
        "the role whose prior written approval is required to use participant support funds for other categories",
    ),
    FieldSpec("psc_approval_channel", "text", "the system through which that prior approval must be requested"),
    FieldSpec("program_officer_email", "text", "the Program Officer's email address"),
    FieldSpec("grants_officer_email", "text", "the Grants Officer's email address"),
)
