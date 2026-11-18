from __future__ import annotations

from sqlalchemy.orm import Session

from ..agents.comparison_agent import compare
from ..models import Component, ComponentSpec
from .component_service import spec_dict, summaries


class ComparisonError(ValueError):
    pass


def compare_components(db: Session, component_ids: list[int]) -> dict:
    ids = list(dict.fromkeys(component_ids))
    if not 2 <= len(ids) <= 5:
        raise ComparisonError("Sélectionnez entre 2 et 5 composants distincts.")
    found = {c.id: c for c in db.query(Component).filter(Component.id.in_(ids)).all()}
    missing = [cid for cid in ids if cid not in found]
    if missing:
        raise LookupError(f"Composant(s) introuvable(s) : {', '.join(map(str, missing))}")
    components = [found[cid] for cid in ids]
    summary = summaries(db, components)
    specs_by_component = [
        [spec_dict(s) for s in db.query(ComponentSpec).filter(ComponentSpec.component_id == c.id).all()]
        for c in components
    ]
    result = compare(summary, specs_by_component)
    return {"components": summary, **result}
