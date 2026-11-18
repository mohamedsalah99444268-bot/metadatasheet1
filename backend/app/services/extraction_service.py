from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..ai.ollama_client import OllamaService
from ..ai.prompts import SpecCandidate, SpecCandidateBatch, build_spec_prompt
from ..ai.structured_output import AIServiceError
from ..parsers.base import BlockInput, ParsedFieldResult
from ..pipeline import build_pipeline_artifacts
from .document_service import get_document_storage_path

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
    )


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
) -> ExtractionOutcome:
    outcome = ExtractionOutcome()
    storage_path = get_document_storage_path(db, document_id)
    if not storage_path:
        outcome.warnings.append("The selected document record no longer points to a readable PDF.")
        return outcome

    try:
        artifacts = build_pipeline_artifacts(storage_path)
        outcome.success = True
    except Exception:
        logger.warning("Deterministic extraction failed for document %s", document_id, exc_info=True)
        outcome.warnings.append("The uploaded PDF could not be parsed by the deterministic extraction stack.")
        return outcome

    for parsed in artifacts.parsed_fields:
        evidence = map_parsed_field(parsed)
        if evidence is not None:
            outcome.specifications.append(evidence)

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
