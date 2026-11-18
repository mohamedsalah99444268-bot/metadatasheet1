"""Electrical-characteristics extraction on real golden datasheets (tests/cases)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.state import SpecificationEvidence
from backend.app.parsers.base import BlockInput
from backend.app.parsers.electrical import canonical_parameter, parse_zone
from backend.app.pipeline import build_pipeline_artifacts
from backend.app.services.extraction_service import (
    apply_identity_rules,
    detect_component_category,
    map_electrical_row,
    map_parsed_field,
)

CASES = Path(__file__).parent / "cases"


@pytest.fixture(scope="module")
def tlv9062():
    return build_pipeline_artifacts(CASES / "tlv9062" / "input.pdf", reference="TLV9062")


@pytest.fixture(scope="module")
def lm2596():
    return build_pipeline_artifacts(CASES / "lm2596" / "input.pdf", reference="LM2596")


@pytest.fixture(scope="module")
def stm32():
    return build_pipeline_artifacts(CASES / "stm32f103c8" / "input.pdf", reference="STM32F103C8")


def rows_of(artifacts, parameter, condition_type=None):
    return [
        row for row in artifacts.electrical_rows
        if row.parameter == parameter and (condition_type is None or row.condition_type == condition_type)
    ]


def one(rows, **expected):
    for row in rows:
        if all(getattr(row, key) == value for key, value in expected.items()):
            return row
    raise AssertionError(f"no row with {expected} in {[(r.min_value, r.typ_value, r.max_value, r.condition) for r in rows]}")


# ---------------------------------------------------------------- op-amp (TLV9062)

def test_tlv9062_has_every_condition_type(tlv9062):
    kinds = {row.condition_type for row in tlv9062.electrical_rows}
    assert {"absolute_maximum", "recommended_operating", "electrical_characteristics"} <= kinds


def test_tlv9062_supply_voltage_limits(tlv9062):
    absolute = one(rows_of(tlv9062, "supply_voltage", "absolute_maximum"), min_value=0.0, max_value=6.0)
    assert absolute.unit == "V" and absolute.page_number == 9
    recommended = one(rows_of(tlv9062, "supply_voltage", "recommended_operating"), min_value=1.8, max_value=5.5)
    assert recommended.page_number == 9


def test_tlv9062_electrical_characteristics(tlv9062):
    vos = one(rows_of(tlv9062, "input_offset_voltage", "electrical_characteristics"), typ_value=0.3, max_value=1.6)
    assert vos.unit == "mV" and vos.page_number == 12 and "VS = 5V" in (vos.condition or "")
    gbw = one(rows_of(tlv9062, "gain_bandwidth"), typ_value=10.0)
    assert gbw.unit == "MHz" and gbw.page_number == 12
    assert one(rows_of(tlv9062, "slew_rate"), typ_value=6.5).unit == "V/µs"
    iq = one(rows_of(tlv9062, "supply_current"), typ_value=538.0, max_value=750.0)
    assert iq.unit == "µA" and iq.page_number == 13
    assert one(rows_of(tlv9062, "esd_hbm"), typ_value=2500.0).condition_type == "general"
    assert one(rows_of(tlv9062, "junction_temperature", "absolute_maximum"), max_value=150.0)


def test_evidence_is_si_normalised(tlv9062):
    row = one(rows_of(tlv9062, "input_offset_voltage", "electrical_characteristics"), typ_value=0.3, max_value=1.6)
    evidence = map_electrical_row(row)
    assert evidence.unit == "V"
    assert evidence.typ_value == pytest.approx(0.0003) and evidence.max_value == pytest.approx(0.0016)
    assert evidence.condition_type == "electrical_characteristics"
    assert evidence.page_number == 12 and "1.6" in evidence.source_text


# ---------------------------------------------------------------- regulator (LM2596)

def test_lm2596_regulator_specs(lm2596):
    assert one(rows_of(lm2596, "supply_voltage", "absolute_maximum"), max_value=45.0).page_number == 5
    assert one(rows_of(lm2596, "supply_voltage", "recommended_operating"), min_value=4.5, max_value=40.0)
    vout = one(rows_of(lm2596, "output_voltage", "electrical_characteristics"), min_value=3.168, typ_value=3.3, max_value=3.432)
    assert vout.page_number == 6 and vout.unit == "V"
    fosc = one(rows_of(lm2596, "switching_frequency"), min_value=127.0, typ_value=150.0, max_value=173.0)
    assert fosc.unit == "kHz" and fosc.page_number == 7
    assert one(rows_of(lm2596, "storage_temperature", "absolute_maximum"), min_value=-65.0, max_value=150.0)


def test_lm2596_identity_rules(lm2596):
    raw = [e for e in (map_parsed_field(p) for p in lm2596.parsed_fields) if e is not None]
    specs = apply_identity_rules(raw, lm2596.blocks, manufacturer="Texas Instruments", reference="LM2596")
    part_numbers = [s.value for s in specs if s.field_name == "part_number"]
    assert part_numbers == ["LM2596"]
    assert [s.value for s in specs if s.field_name == "manufacturer"] == ["Texas Instruments"]
    orderables = [s.value for s in specs if s.field_name == "orderable_part_number"]
    assert orderables and all(value.upper().startswith("LM2596") for value in orderables)
    assert all(s.category == "identity" for s in specs if s.field_name == "orderable_part_number")
    pins = [s.value for s in specs if s.field_name == "pin_count"]
    assert len(pins) <= 1 and all(int(v) > 0 for v in pins)
    packages = [s.value.upper() for s in specs if s.field_name == "package"]
    assert len(packages) == len(set(packages))
    assert next(s.value for s in specs if s.field_name == "component_category") == "voltage_regulator"


# ---------------------------------------------------------------- MCU (STM32F103C8)

def test_stm32_operating_conditions(stm32):
    vdd = one(rows_of(stm32, "supply_voltage", "recommended_operating"), min_value=2.0, max_value=3.6)
    assert vdd.page_number == 38
    hclk = one(rows_of(stm32, "clock_frequency", "recommended_operating"), max_value=72.0)
    assert hclk.unit == "MHz"
    assert one(rows_of(stm32, "supply_voltage", "absolute_maximum"), min_value=-0.3, max_value=4.0).page_number == 37
    # "Max(1)" header + "TA = 85 °C | TA = 105 °C" sub-columns -> one row per sub-column.
    run = rows_of(stm32, "supply_current", "electrical_characteristics")
    assert any(r.max_value == 50.0 and "85" in (r.condition or "") for r in run)
    assert any(r.max_value == 50.3 and "105" in (r.condition or "") for r in run)


def test_stm32_feature_list_and_category(stm32):
    features = {row.parameter: row for row in stm32.electrical_rows if row.parser_rule == "feature_list_regex"}
    assert features["clock_frequency"].max_value == 72.0
    assert (features["supply_voltage"].min_value, features["supply_voltage"].max_value) == (2.0, 3.6)
    # "64 or 128 Kbytes" depends on the variant: no number is invented.
    assert features["flash_size"].typ_value is None and "64 or 128" in features["flash_size"].value_text
    assert detect_component_category(stm32.blocks)[0] == "microcontroller"


def test_stm32_document_number_is_not_a_part_number(stm32):
    raw = [e for e in (map_parsed_field(p) for p in stm32.parsed_fields) if e is not None]
    specs = apply_identity_rules(raw, stm32.blocks, manufacturer="STMicroelectronics", reference="STM32F103C8")
    values = {s.value for s in specs if s.field_name in {"part_number", "orderable_part_number"}}
    assert values == {"STM32F103C8"}
    assert "DS5319" not in values and "UFQFPN48" not in values


# ---------------------------------------------------------------- unit helpers

def test_identity_without_reference_drops_junk():
    blocks = [BlockInput(id=1, page_number=1, text="LM741 Operational Amplifier SNOSC25D", x0=0, y0=0, x1=1, y1=1)]

    def ev(field, value, conf=0.7):
        return SpecificationEvidence(field_name=field, value=value, confidence=conf, page_number=1, source_text=value)

    specs = apply_identity_rules(
        [ev("part_number", "SNOSC25D", 0.9), ev("part_number", "TO-99", 0.8), ev("part_number", "LM741"),
         ev("part_number", "LM741C-MWC", 0.6), ev("pin_count", "0"), ev("pin_count", "8")],
        blocks,
    )
    assert [s.value for s in specs if s.field_name == "part_number"] == ["LM741"]
    assert [s.value for s in specs if s.field_name == "orderable_part_number"] == ["LM741C-MWC"]
    assert [s.value for s in specs if s.field_name == "pin_count"] == ["8"]
    assert next(s.value for s in specs if s.field_name == "component_category") == "op_amp"


def test_zone_parsing_rules():
    assert parse_zone("±22").number == 22.0
    assert parse_zone("–0.3").number == -0.3
    assert parse_zone("5(4)").number == 5.0
    assert parse_zone("VDD+0.3").number is None  # relative limit: text only, never a number
    rng = parse_zone("−0.3 to 7")
    assert (rng.low, rng.high) == (-0.3, 7.0)
    assert parse_zone("—") is None
    assert canonical_parameter("Supply voltage rejection ratio")[0] == "psrr"
    assert canonical_parameter("Junction-to-ambient thermal resistance")[0] == "thermal_resistance_ja"
    assert canonical_parameter("Some unusual thing")[0] == "some_unusual_thing"
