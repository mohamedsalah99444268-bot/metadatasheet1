"""Comparison agent: unit-aware side-by-side comparison of 2..5 components.

Pure function over already-normalised spec dicts (SI values in min/typ/max).
It never fills gaps: missing evidence yields "insufficient_evidence", and
`interchangeable` is True only when every compatibility axis is compatible
AND every core parameter of every component is human accepted/edited."""
from __future__ import annotations

import re
from typing import Any

IDENTITY_SKIP = {"manufacturer", "part_number", "description"}
CORE_PARAMETERS = ("supply_voltage", "current", "temperature_range", "package", "pin_count")
VOLTAGE_PARAMS = ("supply_voltage", "operating_voltage", "input_voltage")
# Supply/quiescent current is what "current compatibility" means for a part; the generic
# "current" key can be an output or short-circuit rating, so it is the last resort.
CURRENT_PARAMS = ("supply_current", "quiescent_current", "current")
# operating_temperature comes from the electrical-table parser and is preferred over the
# legacy identity-parser temperature_range, which can hold garbled ranges ("0 to 3 C").
TEMPERATURE_PARAMS = ("operating_temperature", "temperature_range")
MIN_TEMPERATURE_SPAN_C = 10.0
REVIEWED_OK = {"accepted", "edited"}
CONDITION_PREFERENCE = {"recommended_operating": 0, "electrical_characteristics": 1, "general": 2, "absolute_maximum": 3}
REL_TOLERANCE = 0.01


def _rank(spec: dict) -> tuple:
    return (
        0 if spec.get("validation_status") in REVIEWED_OK else 1,
        CONDITION_PREFERENCE.get(spec.get("condition_type") or "general", 2),
        -(spec.get("confidence") or 0.0),
        spec.get("id") or 0,
    )


def _implausible(spec: dict) -> bool:
    """Degenerate ranges that cannot be a real rating (e.g. "0 to 0 C", "0 to 3 C")."""
    low, high = spec.get("min_value"), spec.get("max_value")
    is_temperature = "temperature" in (spec.get("parameter") or "")
    if low is None or high is None:
        # a temperature *range* needs both ends; a lone "85 °C" is not a range
        return is_temperature and (spec.get("condition_type") != "absolute_maximum")
    if high < low:
        return True
    if (spec.get("unit") or "").endswith("C") and is_temperature:
        return high - low < MIN_TEMPERATURE_SPAN_C
    return False


def best_specs(specs: list[dict]) -> dict[str, dict]:
    """Best non-rejected, plausible spec per parameter."""
    chosen: dict[str, dict] = {}
    usable = (s for s in specs if s.get("validation_status") != "rejected" and not _implausible(s))
    for spec in sorted(usable, key=_rank):
        chosen.setdefault(spec["parameter"], spec)
    return chosen


def _bounds(spec: dict | None) -> tuple[float | None, float | None]:
    if not spec:
        return None, None
    values = [v for v in (spec.get("min_value"), spec.get("typ_value"), spec.get("max_value")) if v is not None]
    if not values:
        return None, None
    return min(values), max(values)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOLERANCE * max(abs(a), abs(b), 1e-12)


def _norm_text(value: str | None) -> str:
    return re.sub(r"[\s\-_]+", "", (value or "").lower())


def _same(a: dict, b: dict) -> bool:
    la, ha = _bounds(a)
    lb, hb = _bounds(b)
    if la is not None and lb is not None:
        if (a.get("unit") or "") != (b.get("unit") or ""):
            return False
        return _close(la, lb) and _close(ha, hb)
    return _norm_text(a.get("value_text")) == _norm_text(b.get("value_text"))


def row_verdict(values: list[dict | None]) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return "missing"
    if len(present) < len(values):
        return "partial"
    first = present[0]
    return "same" if all(_same(first, other) for other in present[1:]) else "different"


def _verdict(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def _first(chosen: dict[str, dict], params: tuple[str, ...]) -> dict | None:
    for param in params:
        if param in chosen:
            return chosen[param]
    return None


def _range_axis(per_component: list[dict[str, dict]], params: tuple[str, ...], names: list[str], unit_label: str) -> dict:
    ranges = []
    for name, chosen in zip(names, per_component):
        low, high = _bounds(_first(chosen, params))
        if low is None:
            return _verdict("insufficient_evidence", f"{name}: aucune valeur {unit_label} exploitable.")
        ranges.append((name, low, high))
    common_low = max(r[1] for r in ranges)
    common_high = min(r[2] for r in ranges)
    detail = "; ".join(f"{n}: {lo:g}–{hi:g} {unit_label}" for n, lo, hi in ranges)
    if common_low > common_high:
        return _verdict("incompatible", f"Aucune plage commune ({detail}).")
    return _verdict("compatible", f"Plage commune {common_low:g}–{common_high:g} {unit_label} ({detail}).")


def _current_axis(per_component: list[dict[str, dict]], names: list[str]) -> dict:
    values = []
    for name, chosen in zip(names, per_component):
        _, high = _bounds(_first(chosen, CURRENT_PARAMS))
        if high is None:
            return _verdict("insufficient_evidence", f"{name}: courant non documenté.")
        values.append((name, high))
    detail = "; ".join(f"{n}: {v:g} A" for n, v in values)
    reference = values[0][1]
    if all(abs(v - reference) <= 0.2 * max(abs(reference), abs(v), 1e-12) for _, v in values):
        return _verdict("compatible", f"Courants à ±20 % ({detail}).")
    return _verdict("incompatible", f"Courants différents ({detail}).")


def _identity_axis(components: list[dict], key: str, label: str) -> dict:
    values = [(c["part_number"], c.get(key)) for c in components]
    missing = [name for name, value in values if value in (None, "")]
    if missing:
        return _verdict("insufficient_evidence", f"{label} inconnu pour : {', '.join(missing)}.")
    normalised = {_norm_text(str(value)) for _, value in values}
    detail = "; ".join(f"{n}: {v}" for n, v in values)
    return _verdict("compatible" if len(normalised) == 1 else "incompatible", detail)


def _interfaces_axis(per_component: list[dict[str, dict]], names: list[str], specs_by_component: list[list[dict]]) -> dict:
    sets = []
    for name, specs in zip(names, specs_by_component):
        interface_specs = [s for s in specs if s.get("category") == "interface" and s.get("validation_status") != "rejected"]
        if not interface_specs:
            return _verdict("insufficient_evidence", f"{name}: aucune interface documentée.")
        sets.append((name, {f"{s['parameter']}={_norm_text(s.get('value_text'))}" for s in interface_specs}))
    reference = sets[0][1]
    if all(item == reference for _, item in sets):
        return _verdict("compatible", "Interfaces identiques.")
    return _verdict("incompatible", "Interfaces différentes : " + "; ".join(f"{n}: {len(s)} entrée(s)" for n, s in sets))


def compare(components: list[dict], specs_by_component: list[list[dict]]) -> dict[str, Any]:
    names = [c["part_number"] for c in components]
    per_component = [best_specs(specs) for specs in specs_by_component]

    parameters: dict[str, dict] = {}
    for chosen in per_component:
        for param, spec in chosen.items():
            if param in IDENTITY_SKIP:
                continue
            parameters.setdefault(param, spec)

    rows = []
    for param in sorted(parameters, key=lambda p: (parameters[p].get("category") or "", p)):
        values = []
        for component, chosen in zip(components, per_component):
            spec = chosen.get(param)
            values.append(
                None
                if spec is None
                else {
                    "component_id": component["id"],
                    "value_text": spec.get("value_text"),
                    "min_value": spec.get("min_value"),
                    "typ_value": spec.get("typ_value"),
                    "max_value": spec.get("max_value"),
                    "page_number": spec.get("page_number"),
                    "validation_status": spec.get("validation_status"),
                    "unit": spec.get("unit"),
                }
            )
        reference = parameters[param]
        rows.append(
            {
                "parameter": param,
                "label": reference.get("label") or param,
                "category": reference.get("category"),
                "unit": reference.get("unit"),
                "values": [
                    None if v is None else {k: v[k] for k in v if k != "unit"} for v in values
                ],
                "verdict": row_verdict(values),
            }
        )

    compatibility = {
        "voltage": _range_axis(per_component, VOLTAGE_PARAMS, names, "V"),
        "current": _current_axis(per_component, names),
        "temperature": _range_axis(per_component, TEMPERATURE_PARAMS, names, "°C"),
        "package": _identity_axis(components, "package", "Boîtier"),
        "pin_count": _identity_axis(components, "pin_count", "Nombre de broches"),
        "interfaces": _interfaces_axis(per_component, names, specs_by_component),
    }

    notes: list[str] = []
    unreviewed = []
    for name, chosen in zip(names, per_component):
        for param in CORE_PARAMETERS:
            spec = chosen.get(param)
            if spec is None:
                unreviewed.append(f"{name}: {param} manquant")
            elif spec.get("validation_status") not in REVIEWED_OK:
                unreviewed.append(f"{name}: {param} non validé ({spec.get('validation_status')})")
    statuses = {axis["status"] for axis in compatibility.values()}
    if "incompatible" in statuses:
        interchangeable: bool | str = False
        notes.append("Au moins un axe est incompatible : composants non interchangeables.")
    elif statuses == {"compatible"} and not unreviewed:
        interchangeable = True
        notes.append("Tous les axes sont compatibles et les paramètres clés sont validés par un humain.")
    else:
        interchangeable = "insufficient_evidence"
        if "insufficient_evidence" in statuses:
            notes.append("Preuves insuffisantes sur au moins un axe de compatibilité.")
    if unreviewed:
        notes.append("Paramètres clés non validés : " + "; ".join(unreviewed[:12]) + ("…" if len(unreviewed) > 12 else ""))
    notes.append("Comparaison basée uniquement sur les valeurs extraites des datasheets ; aucune valeur n'est inventée.")
    return {"rows": rows, "compatibility": compatibility, "interchangeable": interchangeable, "notes": notes}
