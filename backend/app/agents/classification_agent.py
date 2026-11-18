"""Classification agent: assigns a spec category and condition type to every
extracted specification. Deterministic rules first; an optional local Ollama
pass may only re-label specs the rules left as "other" (it never touches
values, units or evidence)."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from .state import AgentEvent, AgentState, SpecificationEvidence

logger = logging.getLogger(__name__)

CATEGORIES = ("electrical", "thermal", "mechanical", "timing", "interface", "memory", "identity", "other")
CONDITION_TYPES = ("absolute_maximum", "recommended_operating", "electrical_characteristics", "general")

IDENTITY_FIELDS = {"manufacturer", "part_number", "description", "family", "series", "grade", "compliance"}
CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("thermal", re.compile(r"temperature|thermal|junction|θ|theta|storage_temp")),
    ("memory", re.compile(r"flash|sram|ram\b|eeprom|memory|rom\b")),
    ("timing", re.compile(r"frequency|clock|_time|delay|slew|speed|baud|rise|fall|period")),
    ("interface", re.compile(r"interface|uart|usart|spi|i2c|i²c|usb|can\b|gpio|ethernet|adc|dac|channels?")),
    ("mechanical", re.compile(r"package|pin_count|pins|dimension|width|height|length|weight|pitch")),
    ("electrical", re.compile(r"voltage|current|power|resistance|capacitance|impedance|gain|offset|noise|drive|leakage|dissipation")),
]

ABS_MAX_RE = re.compile(r"absolute\s*maximum|abs(?:olute)?\.?\s*max|maximum\s+ratings|stress", re.IGNORECASE)
RECOMMENDED_RE = re.compile(r"recommended\s+operating|operating\s+conditions|operating\s+range", re.IGNORECASE)
ELECTRICAL_RE = re.compile(r"electrical\s+characteristics|dc\s+characteristics|ac\s+characteristics", re.IGNORECASE)


def classify_category(field_name: str) -> str:
    name = (field_name or "").lower()
    if name in IDENTITY_FIELDS:
        return "identity"
    for category, pattern in CATEGORY_RULES:
        if pattern.search(name):
            return category
    return "other"


def classify_condition(spec: SpecificationEvidence, category: str | None = None) -> str:
    category = category or classify_category(spec.field_name)
    if category == "identity":
        return "general"
    haystacks = [spec.section, spec.condition, spec.parser_rule, spec.field_name, spec.source_text]
    for text in haystacks:
        if not text:
            continue
        if ABS_MAX_RE.search(text):
            return "absolute_maximum"
        if RECOMMENDED_RE.search(text):
            return "recommended_operating"
        if ELECTRICAL_RE.search(text):
            return "electrical_characteristics"
    name = spec.field_name.lower()
    if name.startswith("operating_") or name == "temperature_range":
        return "recommended_operating"
    if name in {"supply_voltage", "current", "power_dissipation", "frequency"}:
        return "electrical_characteristics"
    return "general"


def classify_specs(specifications: list[SpecificationEvidence]) -> int:
    """Set category / condition_type in place. Returns number of 'other' specs."""
    others = 0
    for spec in specifications:
        if not spec.category:
            spec.category = classify_category(spec.field_name)  # type: ignore[assignment]
        if not spec.condition_type:
            spec.condition_type = classify_condition(spec, spec.category)  # type: ignore[assignment]
        if spec.category == "other":
            others += 1
    return others


class _CategoryLabel(BaseModel):
    field_name: str
    category: str


class _CategoryBatch(BaseModel):
    labels: list[_CategoryLabel] = Field(default_factory=list)


def refine_with_ollama(specifications: list[SpecificationEvidence], service=None) -> int:
    """Ask the local model to label 'other' specs. Only accepts known categories
    for field names that actually exist. Returns number of relabelled specs."""
    pending = sorted({spec.field_name for spec in specifications if spec.category == "other"})
    if not pending:
        return 0
    from ..ai.ollama_client import OllamaService

    service = service or OllamaService()
    if service.check_ollama().status != "available":
        return 0
    prompt = (
        "Classify each datasheet parameter name into exactly one category among "
        f"{', '.join(CATEGORIES)}. Answer JSON {{\"labels\": [{{\"field_name\": str, \"category\": str}}]}}. "
        "Do not add parameters. Parameters: " + ", ".join(pending)
    )
    batch = service.generate_structured(prompt, _CategoryBatch)
    mapping = {
        label.field_name: label.category
        for label in batch.labels
        if label.field_name in pending and label.category in CATEGORIES and label.category != "other"
    }
    changed = 0
    for spec in specifications:
        if spec.category == "other" and spec.field_name in mapping:
            spec.category = mapping[spec.field_name]  # type: ignore[assignment]
            changed += 1
    return changed


def run_classification_agent(state: AgentState) -> AgentState:
    updated = dict(state)
    specifications = list(state.get("specifications", []))
    others = classify_specs(specifications)
    refined = 0
    if others and state.get("ollama_available"):
        try:
            refined = refine_with_ollama(specifications)
        except Exception as exc:  # model is optional; rules already applied
            logger.info("Ollama classification refinement skipped: %s", exc)
    counts: dict[str, int] = {}
    for spec in specifications:
        counts[spec.category or "other"] = counts.get(spec.category or "other", 0) + 1
    summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "no specs"
    updated["specifications"] = specifications
    updated["classification_ok"] = True
    updated["current_agent"] = "classification"
    events = list(updated.get("events", []))
    message = f"Classified {len(specifications)} spec(s): {summary}."
    if refined:
        message += f" Local model relabelled {refined} uncategorised spec(s)."
    events.append(AgentEvent(agent="classification", status="completed", message=message))
    updated["events"] = events
    return updated
