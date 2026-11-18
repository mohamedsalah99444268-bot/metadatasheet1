"""Human review of normalised specs. Every change writes a SpecReviewLog row and
commits in a single transaction."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Component, ComponentSpec, SpecReviewLog, User
from .component_service import label_for, spec_dict, utcnow
from .units import parse_value

EDITABLE_FIELDS = ("value_text", "unit", "min_value", "typ_value", "max_value", "test_condition", "page_number")
CATEGORIES = {"electrical", "thermal", "mechanical", "timing", "interface", "memory", "identity", "other"}
CONDITIONS = {"absolute_maximum", "recommended_operating", "electrical_characteristics", "general"}


class SpecError(ValueError):
    pass


def _snapshot(spec: ComponentSpec) -> dict[str, Any]:
    return {
        "value_text": spec.value_text,
        "unit": spec.unit,
        "min_value": spec.min_value,
        "typ_value": spec.typ_value,
        "max_value": spec.max_value,
        "test_condition": spec.test_condition,
        "page_number": spec.page_number,
        "validation_status": spec.validation_status,
    }


def _user_id(user: User | None) -> int | None:
    return getattr(user, "id", None)


def _log(db: Session, spec: ComponentSpec, action: str, old: dict | None, comment: str | None, user: User | None) -> None:
    db.add(
        SpecReviewLog(
            spec_id=spec.id,
            action=action,
            old_value=old,
            new_value=_snapshot(spec),
            comment=comment,
            user_id=_user_id(user),
        )
    )


def _touch(spec: ComponentSpec, status: str, comment: str | None, user: User | None) -> None:
    spec.validation_status = status
    if comment is not None:
        spec.reviewer_comment = comment
    spec.reviewed_by = _user_id(user)
    spec.reviewed_at = utcnow()
    if spec.component is not None:
        spec.component.updated_at = utcnow()


def _commit(db: Session, spec: ComponentSpec) -> dict:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(spec)
    return spec_dict(spec)


def set_status(db: Session, spec: ComponentSpec, action: str, comment: str | None, user: User | None) -> dict:
    old = _snapshot(spec)
    _touch(spec, "accepted" if action == "accept" else "rejected", comment, user)
    db.flush()
    _log(db, spec, action, old, comment, user)
    return _commit(db, spec)


def edit(db: Session, spec: ComponentSpec, changes: dict[str, Any], user: User | None) -> dict:
    comment = changes.pop("comment", None)
    changes = {key: value for key, value in changes.items() if key in EDITABLE_FIELDS}
    if not changes:
        raise SpecError("Aucun champ modifiable fourni.")
    if "value_text" in changes and not str(changes["value_text"] or "").strip():
        raise SpecError("value_text ne peut pas être vide.")
    old = _snapshot(spec)
    for key, value in changes.items():
        setattr(spec, key, value)
    numeric_given = any(key in changes for key in ("min_value", "typ_value", "max_value"))
    if "value_text" in changes and not numeric_given:
        parsed = parse_value(spec.value_text, spec.unit)
        if parsed.has_number:
            spec.min_value, spec.typ_value, spec.max_value = parsed.min_value, parsed.typ_value, parsed.max_value
            spec.unit = changes.get("unit") or parsed.unit or spec.unit
    _validate_range(spec)
    _touch(spec, "edited", comment, user)
    db.flush()
    _log(db, spec, "edit", old, comment, user)
    return _commit(db, spec)


def _validate_range(spec: ComponentSpec) -> None:
    values = [v for v in (spec.min_value, spec.typ_value, spec.max_value) if v is not None]
    if values != sorted(values):
        raise SpecError("Valeurs incohérentes : il faut min ≤ typ ≤ max.")


def add(db: Session, component: Component, payload: dict[str, Any], user: User | None) -> dict:
    parameter = str(payload.get("parameter") or "").strip()
    value_text = str(payload.get("value_text") or "").strip()
    if not parameter or not value_text:
        raise SpecError("parameter et value_text sont obligatoires.")
    category = payload.get("category") or "other"
    condition = payload.get("condition_type") or "general"
    if category not in CATEGORIES:
        raise SpecError(f"Catégorie inconnue : {category}")
    if condition not in CONDITIONS:
        raise SpecError(f"condition_type inconnu : {condition}")
    parsed = parse_value(value_text, payload.get("unit"))
    spec = ComponentSpec(
        component_id=component.id,
        document_id=component.document_id,
        parameter=parameter,
        label=payload.get("label") or label_for(parameter),
        category=category,
        condition_type=condition,
        value_text=value_text,
        unit=payload.get("unit") or parsed.unit,
        min_value=payload.get("min_value") if payload.get("min_value") is not None else parsed.min_value,
        typ_value=payload.get("typ_value") if payload.get("typ_value") is not None else parsed.typ_value,
        max_value=payload.get("max_value") if payload.get("max_value") is not None else parsed.max_value,
        page_number=payload.get("page_number"),
        source_text=payload.get("source_text"),
        confidence=1.0,
        extraction_method="manual",
        validation_status="accepted",
        reviewer_comment=payload.get("comment"),
        reviewed_by=_user_id(user),
        reviewed_at=utcnow(),
    )
    _validate_range(spec)
    db.add(spec)
    component.updated_at = utcnow()
    db.flush()
    db.add(
        SpecReviewLog(spec_id=spec.id, action="add", old_value=None, new_value=_snapshot(spec), comment=payload.get("comment"), user_id=_user_id(user))
    )
    return _commit(db, spec)


def log_entries(db: Session, spec: ComponentSpec) -> list[dict]:
    rows = db.query(SpecReviewLog).filter(SpecReviewLog.spec_id == spec.id).order_by(SpecReviewLog.id).all()
    return [
        {
            "action": row.action,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "comment": row.comment,
            "created_at": row.created_at,
            "user_email": row.user.email if row.user is not None else None,
        }
        for row in rows
    ]
