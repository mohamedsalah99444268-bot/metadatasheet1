from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from ..ai.ollama_client import OllamaService
from ..ai.prompts import SpecCandidate, SpecCandidateBatch, build_spec_prompt
from ..ai.structured_output import AIServiceError
from ..parsers.base import BlockInput, ParsedFieldResult
from ..parsers.consolidator import PACKAGE_PATTERN
from ..parsers.electrical import PARAMETER_CATEGORY, ElectricalRow
from ..pipeline import build_pipeline_artifacts
from .document_service import get_document_storage_path
from .units import si_unit

logger = logging.getLogger(__name__)

FIELD_TYPE_TO_SPEC = {
    "manufacturer": "manufacturer",
    "part_number": "part_number",
    "title": "description",
    "package_name": "package",
    "package_code": "package",
    "pin_count": "pin_count",
    "operating_voltage": "operating_voltage",
    "supply_voltage": "supply_voltage",
    "current": "current",
    "power": "power_dissipation",
    "frequency": "frequency",
    "temperature_grade": "temperature_range",
}

UNIT_BY_SPEC = {
    "pin_count": "pins",
    "temperature_range": "°C",
}


@dataclass
class ExtractionOutcome:
    specifications: list = field(default_factory=list)
    ollama_available: bool = False
    warnings: list[str] = field(default_factory=list)
    success: bool = False


def map_parsed_field(parsed: ParsedFieldResult):
    from ..agents.state import SpecificationEvidence

    field_name = FIELD_TYPE_TO_SPEC.get(parsed.field_type)
    if not field_name:
        return None
    if field_name == "pin_count":
        digits = re.search(r"\d+", parsed.value or "")
        if not digits or int(digits.group()) <= 0:
            return None
    return SpecificationEvidence(
        field_name=field_name,
        value=parsed.value,
        unit=UNIT_BY_SPEC.get(field_name),
        page_number=parsed.page_number,
        source_text=parsed.source_text or None,
        bbox=[parsed.x0, parsed.y0, parsed.x1, parsed.y1],
        extraction_method="deterministic",
        confidence=max(0.0, min(1.0, float(parsed.confidence))),
        validation_status="needs_review",
        parser_rule=parsed.parser_rule,
        section=getattr(parsed, "section_name", None),
    )


def _scaled(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return float(f"{value * factor:.12g}")


def map_electrical_row(row: ElectricalRow):
    """One table row (parameter + condition) -> one evidence with SI min/typ/max."""
    from ..agents.state import SpecificationEvidence

    factor, unit = si_unit(row.unit)
    return SpecificationEvidence(
        field_name=row.parameter,
        label=row.label,
        value=row.value_text,
        unit=unit,
        min_value=_scaled(row.min_value, factor),
        typ_value=_scaled(row.typ_value, factor),
        max_value=_scaled(row.max_value, factor),
        page_number=row.page_number,
        source_text=row.source_text,
        bbox=row.bbox,
        extraction_method="deterministic",
        confidence=row.confidence,
        validation_status="needs_review",
        parser_rule=row.parser_rule,
        condition=row.condition,
        section=row.section,
        category=PARAMETER_CATEGORY.get(row.parameter),
        condition_type=row.condition_type,
    )


# ---------------------------------------------------------------- identity rules

DOC_NUMBER_RE = re.compile(
    r"^(S[A-Z]{3,4}\d{2,4}[A-Z]{0,2}|DS\d{3,}[A-Z0-9]*|DOCID\d+|AN\d{3,}|UM\d{3,}|RM\d{3,}|ES\d{4,})$",
    re.IGNORECASE,
)
EXTRA_PACKAGE_RE = re.compile(r"^(TO-?\d+[A-Z]*|CDIP|PDIP|SOIC|SOP|SSOP|TSSOP|MSOP|QFN|DFN|BGA|LGA)(-?\d+)?$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _is_junk_part_number(value: str) -> bool:
    upper = value.strip().upper()
    return bool(DOC_NUMBER_RE.match(upper) or PACKAGE_PATTERN.match(upper) or EXTRA_PACKAGE_RE.match(upper))


def _find_in_blocks(blocks: list[BlockInput], needle: str) -> BlockInput | None:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(needle)}", re.IGNORECASE)
    for block in sorted(blocks, key=lambda b: (b.page_number, b.y0)):
        if pattern.search(block.text):
            return block
    return None


CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("microcontroller", re.compile(r"microcontroller|\bmcu\b|cortex[\s®-]*m\d|\b(8|16|32)-bit\s+(avr|risc|arm)|risc\s+architecture", re.I)),
    ("op_amp", re.compile(r"operational\s+amplifiers?|\bop[\s-]?amps?\b", re.I)),
    ("voltage_regulator", re.compile(r"regulator|\bldo\b|step[\s-]down|step[\s-]up|buck|boost\s+converter|dc[\s/-]?dc", re.I)),
    ("mosfet", re.compile(r"mosfet|hexfet|power\s+fet|n-channel|p-channel", re.I)),
    ("rf", re.compile(r"\brf\b|transceiver.*ghz|\d(\.\d)?\s*ghz|radio|wireless", re.I)),
    ("memory", re.compile(r"\beeprom\b|\bsram\b|\bdram\b|\bfram\b|flash\s+memory\s+device|serial\s+flash", re.I)),
    ("sensor", re.compile(r"sensor|accelerometer|gyroscope|magnetometer|thermometer", re.I)),
    ("interface", re.compile(r"transceiver|\buart\b|rs-?485|rs-?232|\bcan\s+(bus|transceiver)|i2c[\s-]bus|level[\s-](shifter|translator)|usb\s+to", re.I)),
    ("logic", re.compile(r"\bbuffer\b|\bgates?\b|flip[\s-]flop|multiplexer|bus\s+transceiver|voltage[\s-]level\s+translat|\blogic\b|clock\s+generator", re.I)),
]


def detect_component_category(blocks: list[BlockInput]) -> tuple[str, BlockInput | None]:
    """Category from the title/description on the first page (title words weigh more)."""
    first = sorted((b for b in blocks if b.page_number == 1), key=lambda b: b.y0)
    if not first:
        return "other", None
    title = " ".join(b.text for b in first[:8])[:800]
    body = " ".join(b.text for b in first)[:6000]
    scores: Counter = Counter()
    for order, (category, pattern) in enumerate(CATEGORY_RULES):
        hits = 3 * len(pattern.findall(title)) + len(pattern.findall(body))
        if hits:
            scores[category] = hits * 100 - order  # ties: rule order
    if not scores:
        return "other", None
    category = scores.most_common(1)[0][0]
    pattern = dict(CATEGORY_RULES)[category]
    evidence = next((b for b in first if pattern.search(b.text)), first[0])
    return category, evidence


def apply_identity_rules(
    specs: list,
    blocks: list[BlockInput],
    *,
    manufacturer: str | None = None,
    reference: str | None = None,
) -> list:
    """User-supplied manufacturer/reference win when the document mentions them;
    orderable codes become `orderable_part_number` specs; junk candidates are dropped."""
    from ..agents.state import SpecificationEvidence

    manufacturer = (manufacturer or "").strip()
    reference = (reference or "").strip()
    others = []
    seen_other: set[tuple[str, str]] = set()
    for spec in specs:
        if spec.field_name in {"part_number", "manufacturer", "pin_count", "package"}:
            continue
        if spec.field_name == "temperature_range" and not re.search(r"\d", spec.value or ""):
            continue
        key = (spec.field_name, " ".join((spec.value or "").upper().split()))
        if key in seen_other:
            continue
        seen_other.add(key)
        others.append(spec)
    part_numbers = [s for s in specs if s.field_name == "part_number" and not _is_junk_part_number(s.value)]
    manufacturers = [s for s in specs if s.field_name == "manufacturer"]
    pin_counts = [s for s in specs if s.field_name == "pin_count"]
    packages = [s for s in specs if s.field_name == "package"]
    result: list = []

    # Manufacturer
    mfr_block = _find_in_blocks(blocks, manufacturer) if manufacturer else None
    if mfr_block is not None:
        result.append(
            SpecificationEvidence(
                field_name="manufacturer", value=manufacturer, page_number=mfr_block.page_number,
                source_text=mfr_block.text[:200], bbox=[mfr_block.x0, mfr_block.y0, mfr_block.x1, mfr_block.y1],
                confidence=0.95, validation_status="needs_review", parser_rule="user_reference_in_document",
                category="identity", condition_type="general",
            )
        )
    elif manufacturers:
        result.append(max(manufacturers, key=lambda s: s.confidence))

    # Part number + orderable codes
    ref_block = _find_in_blocks(blocks, reference) if reference else None
    ordered = sorted(part_numbers, key=lambda s: s.confidence, reverse=True)
    if ref_block is not None:
        base = _norm(reference)
        result.append(
            SpecificationEvidence(
                field_name="part_number", value=reference, page_number=ref_block.page_number,
                source_text=ref_block.text[:200], bbox=[ref_block.x0, ref_block.y0, ref_block.x1, ref_block.y1],
                confidence=0.95, validation_status="needs_review", parser_rule="user_reference_in_document",
                category="identity", condition_type="general",
            )
        )
        orderables = [s for s in ordered if _norm(s.value).startswith(base) and _norm(s.value) != base]
    elif ordered:
        # Reference absent from the text (e.g. "STM32F103C8T6" for a datasheet naming
        # "STM32F103C8"): prefer the longest candidate the reference starts with.
        prefixes = [s for s in ordered if reference and _norm(reference).startswith(_norm(s.value))]
        primary = max(prefixes, key=lambda s: len(_norm(s.value))) if prefixes else ordered[0]
        result.append(primary)
        stem = _norm(primary.value)
        orderables = [s for s in ordered if _norm(s.value).startswith(stem) and _norm(s.value) != stem]
    else:
        orderables = []
    seen_orderable: set[str] = set()
    for spec in orderables:
        key = _norm(spec.value)
        if key in seen_orderable:
            continue
        seen_orderable.add(key)
        result.append(spec.model_copy(update={"field_name": "orderable_part_number", "category": "identity", "condition_type": "general"}))

    # Pin count: never 0, one value (the most common)
    valid_pins = [s for s in pin_counts if (m := re.search(r"\d+", s.value or "")) and int(m.group()) > 0]
    if valid_pins:
        common = Counter(re.search(r"\d+", s.value).group() for s in valid_pins).most_common(1)[0][0]
        result.append(next(s for s in valid_pins if re.search(r"\d+", s.value).group() == common))

    # Packages: distinct values, most common first
    counts = Counter(s.value.strip().upper() for s in packages if (s.value or "").strip())
    seen_pkg: set[str] = set()
    for spec in sorted(packages, key=lambda s: (-counts[s.value.strip().upper()], s.page_number or 0)):
        key = spec.value.strip().upper()
        if not key or key in seen_pkg:
            continue
        seen_pkg.add(key)
        result.append(spec)

    # Category from the first page
    category, cat_block = detect_component_category(blocks)
    if cat_block is not None:
        result.append(
            SpecificationEvidence(
                field_name="component_category", value=category, page_number=cat_block.page_number,
                source_text=cat_block.text[:200], bbox=[cat_block.x0, cat_block.y0, cat_block.x1, cat_block.y1],
                confidence=0.7, validation_status="needs_review", parser_rule="category_keywords",
                category="identity", condition_type="general",
            )
        )
    return result + others


def ground_candidate(candidate: SpecCandidate, blocks: list[BlockInput]):
    from ..agents.state import SpecificationEvidence

    wanted = " ".join(candidate.source_text.split())
    for block in blocks:
        available = " ".join(block.text.split())
        if block.page_number != candidate.page_number or wanted not in available:
            continue
        return SpecificationEvidence(
            field_name=candidate.field_name,
            value=candidate.value.strip(),
            unit=candidate.unit.strip() if candidate.unit and candidate.unit.strip() else None,
            page_number=block.page_number,
            source_text=candidate.source_text,
            bbox=[block.x0, block.y0, block.x1, block.y1],
            extraction_method="ollama",
            confidence=0.6,
            validation_status="needs_review",
            parser_rule=f"ollama_spec_extraction:{candidate.value_kind}",
            condition=candidate.condition,
            value_kind=candidate.value_kind,
        )
    return None


def extract_specifications(
    db,
    document_id: int,
    ollama_service: OllamaService | None = None,
    *,
    manufacturer: str | None = None,
    reference: str | None = None,
) -> ExtractionOutcome:
    outcome = ExtractionOutcome()
    storage_path = get_document_storage_path(db, document_id)
    if not storage_path:
        outcome.warnings.append("The selected document record no longer points to a readable PDF.")
        return outcome

    try:
        artifacts = build_pipeline_artifacts(storage_path, reference=reference)
        outcome.success = True
    except Exception:
        logger.warning("Deterministic extraction failed for document %s", document_id, exc_info=True)
        outcome.warnings.append("The uploaded PDF could not be parsed by the deterministic extraction stack.")
        return outcome

    identity: list = []
    for parsed in artifacts.parsed_fields:
        evidence = map_parsed_field(parsed)
        if evidence is not None:
            identity.append(evidence)
    outcome.specifications.extend(
        apply_identity_rules(identity, artifacts.blocks, manufacturer=manufacturer, reference=reference)
    )
    outcome.specifications.extend(map_electrical_row(row) for row in artifacts.electrical_rows)

    service = ollama_service or OllamaService()
    health = service.check_ollama()
    outcome.ollama_available = health.status == "available"

    if not outcome.ollama_available:
        outcome.warnings.append(health.message)
        return outcome

    try:
        batch = service.generate_structured(build_spec_prompt(artifacts.blocks), SpecCandidateBatch)
        for candidate in batch.candidates:
            evidence = ground_candidate(candidate, artifacts.blocks)
            if evidence is not None:
                outcome.specifications.append(evidence)
        rejected = len(batch.candidates) - sum(
            1 for spec in outcome.specifications if spec.extraction_method == "ollama"
        )
        if rejected:
            outcome.warnings.append(f"Rejected {rejected} model candidate(s) without exact source evidence.")
    except AIServiceError as exc:
        outcome.warnings.append(exc.public_message)
    except Exception:
        logger.warning("Local model extraction failed for document %s", document_id, exc_info=True)
        outcome.warnings.append("Local model extraction failed; deterministic fields were retained.")

    return outcome
