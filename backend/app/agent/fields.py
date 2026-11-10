"""A guide to each record kind's fields, built from the contract models.

The write tools take a kind and a list of values by field path, so the model has to know each
kind's fields. Building the guide from the contract models keeps it in step with #14: a renamed
or added field shows up here without a prompt edit.
"""

import types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from .adapter import FACT_RECORD_MODELS, TERM_RECORD_MODELS

_CITED = {
    "CitedText": "cited text",
    "CitedMoney": "cited money",
    "CitedDate": "cited date",
    "CitedDecimal": "cited number",
}


def _describe(annotation: Any, prefix: str) -> list[str]:
    args = [a for a in get_args(annotation) if a is not type(None)]
    if get_origin(annotation) in (Union, types.UnionType) and len(args) == 1:
        annotation = args[0]
    name = getattr(annotation, "__name__", str(annotation))
    if name in _CITED:
        return [f"{prefix} ({_CITED[name]})"]
    if get_origin(annotation) is list:
        inner = get_args(annotation)[0]
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            return [
                line
                for n, f in inner.model_fields.items()
                for line in _describe(f.annotation, f"{prefix}[i].{n}")
            ]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [
            line
            for n, f in annotation.model_fields.items()
            for line in _describe(f.annotation, f"{prefix}.{n}")
        ]
    if name == "BudgetCategory":
        return [f"{prefix}: the tool's category argument, one of NSF's categories"]
    return [f"{prefix}: the tool's {prefix} argument, plain text"]


def _kind_line(kind: str, model: type[BaseModel]) -> str:
    required: list[str] = []
    optional: list[str] = []
    for name, f in model.model_fields.items():
        if name == "kind":
            continue
        target = required if f.is_required() else optional
        target += _describe(f.annotation, name)
    parts = [f"- {kind}: " + "; ".join(required)]
    if optional:
        parts.append("optional: " + "; ".join(optional))
    return ". ".join(parts) + "."


def field_guide(models: dict[str, type[BaseModel]]) -> str:
    return "\n".join(_kind_line(kind, model) for kind, model in models.items())


FACT_FIELDS = field_guide(FACT_RECORD_MODELS)
TERM_FIELDS = field_guide(TERM_RECORD_MODELS)
