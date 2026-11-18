"""Unit parsing / SI normalisation for datasheet values.

parse_value("2.0 V to 3.6 V") -> ParsedValue(min=2.0, typ=None, max=3.6, unit="V")
parse_value("10 mA") -> ParsedValue(min=None, typ=0.01, max=None, unit="A")
Never invents numbers: anything that cannot be parsed yields all-None values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PREFIXES = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# base unit token (case-sensitive where it matters) -> canonical SI unit
BASE_UNITS = {
    "V": "V",
    "A": "A",
    "W": "W",
    "Hz": "Hz",
    "HZ": "Hz",
    "hz": "Hz",
    "s": "s",
    "F": "F",
    "Ω": "Ω",
    "ohm": "Ω",
    "Ohm": "Ω",
    "B": "B",
    "bit": "bit",
    "bps": "bps",
}

TEMPERATURE_RE = re.compile(r"°\s*C|ºC|\bdeg\s*C\b|\bdegC\b|\bcelsius\b", re.IGNORECASE)
PIN_RE = re.compile(r"\bpins?\b|\bleads?\b|\bballs?\b", re.IGNORECASE)
NUMBER = r"[-+−–]?\d+(?:[.,]\d+)?"
UNIT_TOKEN_RE = re.compile(
    r"^\s*(?P<prefix>[pnuµμmkKMG]?)(?P<base>Hz|HZ|hz|V|A|W|s|F|Ω|ohm|Ohm|B|bit|bps)\b"
)
NUM_UNIT_RE = re.compile(rf"(?P<num>{NUMBER})\s*(?P<unit>[pnuµμmkKMG]?(?:Hz|HZ|hz|V|A|W|s|F|Ω|ohm|Ohm|B|bit|bps)\b)?")
RANGE_SEP_RE = re.compile(rf"(?P<a>{NUMBER})\s*(?P<ua>[^\d\s,;]*?)\s*(?:to|\.\.\.?|…|~|-|–|—|/)\s*(?P<b>{NUMBER})")


@dataclass(frozen=True)
class ParsedValue:
    min_value: float | None = None
    typ_value: float | None = None
    max_value: float | None = None
    unit: str | None = None

    @property
    def has_number(self) -> bool:
        return any(v is not None for v in (self.min_value, self.typ_value, self.max_value))


def _to_float(raw: str) -> float:
    return float(raw.replace("−", "-").replace("–", "-").replace(",", "."))


def split_unit(token: str | None) -> tuple[float, str | None]:
    """Return (multiplier, canonical SI unit) for a unit token such as 'mA', 'MHz', '°C'."""
    if not token:
        return 1.0, None
    token = token.strip()
    if TEMPERATURE_RE.search(token) or token.upper() in {"C", "DEGC"}:
        return 1.0, "°C"
    if PIN_RE.search(token):
        return 1.0, "pins"
    match = UNIT_TOKEN_RE.match(token)
    if not match:
        return 1.0, None
    prefix, base = match.group("prefix"), match.group("base")
    # "m" before s/A/V/W/Hz is milli; "M" mega; ambiguous 'B' keeps prefixes (kB, MB).
    return PREFIXES.get(prefix, 1.0), BASE_UNITS.get(base, base)


def normalise(value: float, unit_token: str | None) -> tuple[float, str | None]:
    factor, unit = split_unit(unit_token)
    return value * factor, unit


def _clean(value: float | None) -> float | None:
    if value is None:
        return None
    return float(f"{value:.12g}")


def parse_value(text: str | None, declared_unit: str | None = None, value_kind: str = "single") -> ParsedValue:
    """Parse a datasheet value string into SI min/typ/max.

    value_kind: single|minimum|typical|maximum (from extraction). A single
    number with kind 'single' is stored as typical.
    """
    if not text:
        return ParsedValue(unit=split_unit(declared_unit)[1])
    raw = " ".join(str(text).split())

    # Unit detection: explicit tokens in text win over the declared unit.
    unit_token: str | None = None
    if TEMPERATURE_RE.search(raw):
        unit_token = "°C"
    elif PIN_RE.search(raw):
        unit_token = "pins"
    else:
        for match in NUM_UNIT_RE.finditer(raw):
            if match.group("unit"):
                unit_token = match.group("unit")
                break
    if unit_token is None:
        unit_token = declared_unit

    # Collect numbers with their own (optional) unit tokens.
    numbers: list[float] = []
    for match in NUM_UNIT_RE.finditer(raw):
        num = _to_float(match.group("num"))
        token = match.group("unit") or unit_token
        numbers.append(normalise(num, token)[0])
    unit = split_unit(unit_token)[1]
    if not numbers:
        return ParsedValue(unit=unit)

    range_match = RANGE_SEP_RE.search(raw)
    # "-40 to 85" / "2.0V-3.6V": take both ends from the range match itself so the
    # separator dash is never read as a minus sign.
    if range_match:
        a_unit = range_match.group("ua") or unit_token
        if not split_unit(a_unit)[1]:
            a_unit = unit_token
        low = normalise(_to_float(range_match.group("a")), a_unit)[0]
        high = normalise(_to_float(range_match.group("b")), unit_token)[0]
        if low > high:
            low, high = high, low
        return ParsedValue(min_value=_clean(low), max_value=_clean(high), unit=unit)

    first = _clean(numbers[0])
    if value_kind == "minimum":
        return ParsedValue(min_value=first, unit=unit)
    if value_kind == "maximum":
        return ParsedValue(max_value=first, unit=unit)
    return ParsedValue(typ_value=first, unit=unit)


def unit_family(unit: str | None) -> str | None:
    return {"V": "voltage", "A": "current", "W": "power", "Hz": "frequency", "°C": "temperature", "s": "time",
            "F": "capacitance", "Ω": "resistance", "B": "memory", "bit": "memory", "pins": "count"}.get(unit or "")


SI_UNIT_RE = re.compile(r"^[pnuµμmkKMG]?(?:V|A|W|Hz|s|F|Ω)$")


def si_unit(unit: str | None) -> tuple[float, str | None]:
    """(multiplier, unit) for a table unit column. Only simple SI units are scaled;
    compound units (V/mV, V/µs, °C/W, dB, %, µV/°C) are kept verbatim."""
    if not unit:
        return 1.0, None
    token = unit.strip().replace("μ", "µ")
    if TEMPERATURE_RE.fullmatch(token) or token in {"°C", "ºC", "C"}:
        return 1.0, "°C"
    if SI_UNIT_RE.match(token):
        return split_unit(token)
    return 1.0, token


def evidence_value(spec) -> ParsedValue:
    """min/typ/max for a SpecificationEvidence: explicit table values win over text parsing."""
    if getattr(spec, "has_explicit_values", False):
        return ParsedValue(min_value=spec.min_value, typ_value=spec.typ_value, max_value=spec.max_value, unit=spec.unit)
    return parse_value(spec.value, spec.unit, spec.value_kind)
