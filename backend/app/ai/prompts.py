from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..parsers.base import BlockInput
from .structured_output import structured_prompt

SpecFieldName = Literal[
    "manufacturer",
    "part_number",
    "description",
    "package",
    "pin_count",
    "operating_voltage",
    "supply_voltage",
    "input_voltage",
    "output_voltage",
    "current",
    "power_dissipation",
    "frequency",
    "temperature_range",
    "communication_interfaces",
    "electrical_characteristics",
    "absolute_maximum_ratings",
    "recommended_operating_conditions",
    "pin_configuration",
]

KEYWORDS = (
    "manufacturer",
    "part number",
    "ordering",
    "description",
    "package",
    "pin",
    "voltage",
    "vcc",
    "vdd",
    "vin",
    "vout",
    "current",
    "power",
    "dissipation",
    "frequency",
    "mhz",
    "ghz",
    "temperature",
    "interface",
    "i2c",
    "spi",
    "uart",
    "usb",
    "can",
    "adc",
    "dac",
    "absolute maximum",
    "recommended operating",
    "operating conditions",
    "electrical characteristics",
)


class SpecCandidate(BaseModel):
    field_name: SpecFieldName
    value: str = Field(min_length=1)
    unit: str | None = None
    condition: str | None = None
    value_kind: Literal["typical", "minimum", "maximum", "single"] = "single"
    source_text: str = Field(min_length=1)
    page_number: int = Field(ge=1)


class SpecCandidateBatch(BaseModel):
    candidates: list[SpecCandidate] = Field(default_factory=list)


def select_prompt_blocks(blocks: list[BlockInput], limit: int = 40) -> list[BlockInput]:
    matched = [block for block in blocks if any(keyword in block.text.lower() for keyword in KEYWORDS)]
    selected = matched or blocks
    return selected[:limit]


def build_spec_prompt(blocks: list[BlockInput]) -> str:
    selected = select_prompt_blocks(blocks)
    lines = []
    for block in selected:
        text = " ".join(block.text.split())[:600]
        lines.append(f"[page {block.page_number}] {text}")
    instruction = (
        "Extract only technical specifications explicitly present in the datasheet text blocks. "
        "Allowed fields are the values in the schema. Copy source_text exactly from one block on the stated "
        "page, never paraphrase it, and never copy the page marker. Keep minimum, typical and maximum values "
        "separate using value_kind. Keep absolute maximum ratings and recommended operating conditions in "
        "their distinct fields. Never guess, infer, normalize, or invent values, units, pages, or conditions. "
        "Return an empty candidates list when a field is not explicitly supported."
    )
    body = "\n".join(lines) if lines else "No text blocks are available."
    return structured_prompt(f"{instruction}\n\nDatasheet text blocks:\n{body}", SpecCandidateBatch)
