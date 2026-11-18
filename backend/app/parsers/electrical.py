"""Table-aware extraction of electrical characteristics.

Datasheets publish their numeric specifications in a handful of standard
tables (Absolute Maximum Ratings, Recommended Operating Conditions, ESD
Ratings, Thermal Information, Electrical / DC / AC / Switching
Characteristics, Timing Requirements). This module:

1. Tracks the current datasheet section from heading / "Table N." lines of the
   already-extracted text blocks (cheap, whole document).
2. Picks a bounded set of candidate pages (inside a relevant section AND
   containing MIN/TYP/MAX/VALUE + UNIT header words).
3. On those pages only, re-reads word positions and PyMuPDF table cells. The
   header line gives the x position of the MIN / TYP / MAX / VALUE / UNIT
   columns; every number is assigned to the nearest header column by its
   x position (find_tables often merges those columns), while row spans
   (parameter, test condition, unit cells covering several sub-rows) come from
   the table cells. When find_tables misses a table, aligned text lines below
   the header are parsed instead.

Rows that cannot be parsed are skipped; values are never invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .base import BlockInput

MAX_CANDIDATE_PAGES = 80
MAX_ROWS = 1500

# ---------------------------------------------------------------- sections

SECTION_TO_CONDITION = {
    "absolute_maximum": "absolute_maximum",
    "recommended_operating": "recommended_operating",
    "electrical_characteristics": "electrical_characteristics",
    "thermal": "general",
    "esd": "general",
}

STRONG_SECTION_RULES: list[tuple[str, re.Pattern]] = [
    ("absolute_maximum", re.compile(r"absolute\s+maximum(\s+ratings)?|maximum\s+ratings", re.I)),
    ("esd", re.compile(r"\besd\s+(ratings|characteristics|protection)|electrostatic\s+discharge\s+(ratings|characteristics)", re.I)),
    ("thermal", re.compile(r"thermal\s+(information|metrics?|resistance)", re.I)),
    (
        "recommended_operating",
        re.compile(r"recommended\s+operating\s+conditions|general\s+operating\s+conditions|^operating\s+conditions\b", re.I),
    ),
    (
        "electrical_characteristics",
        re.compile(
            r"electrical\s+(characteristics|specifications)|\b(dc|ac)\s+(electrical\s+)?characteristics|switching\s+characteristics|"
            r"timing\s+(requirements|characteristics)|power\s+supply\s+(characteristics|requirements)",
            re.I,
        ),
    ),
]
WEAK_ELECTRICAL_RE = re.compile(r"characteristics|current\s+consumption|consumption", re.I)
HEADING_PREFIX_RE = re.compile(r"^(?:(?P<num>\d+(?:\.\d+)*)\.?\s+|(?P<table>table\s+[\w.\-]+\.?)\s*)", re.I)
FOOTER_RE = re.compile(r"submit|feedback|copyright|©|www\.|\brev\b|page\s+\d", re.I)
TOC_RE = re.compile(r"\.{4,}|(?:\s\.){3,}|…{2,}")
# Part-number-like tokens used to recognise per-variant tables ("Electrical Characteristics: LM741A").
VARIANT_TOKEN_RE = re.compile(r"\b([A-Z]{2,}[a-z]{0,4}\d{2,}[A-Z0-9/]*)\b")


@dataclass
class SectionEvent:
    page_number: int
    y: float
    section: str | None
    title: str


def _heading_section(line: str) -> tuple[str, str | None, bool] | None:
    """Return (kind, section, is_top_level) for a heading-like line, else None.

    kind: "strong" (named section), "weak" (generic characteristics title),
    "reset" (another top-level chapter).
    """
    text = " ".join(line.split())
    if not text or len(text) > 160 or TOC_RE.search(text):
        return None
    prefix = HEADING_PREFIX_RE.match(text)
    remainder = text[prefix.end():] if prefix else text
    is_table = bool(prefix and prefix.group("table"))
    number = prefix.group("num") if prefix and prefix.group("num") else None
    if not prefix and len(text) > 70:
        return None
    if number and len(text) > 110:
        return None
    for section, pattern in STRONG_SECTION_RULES:
        if section == "recommended_operating":
            if pattern.search(remainder) or re.search(r"operating\s+conditions", remainder, re.I):
                return ("strong", section, False)
            continue
        if pattern.search(remainder):
            return ("strong", section, False)
    if (is_table or number) and WEAK_ELECTRICAL_RE.search(remainder):
        return ("weak", "electrical_characteristics", False)
    if (
        number
        and "." not in number
        and re.match(r"[A-Z][a-z]", remainder or "")
        and len(text) <= 60
        and not FOOTER_RE.search(remainder)
        and len(remainder.split()) <= 6
        and not re.search(r"[,.;:=()\d]", remainder)
    ):
        return ("reset", None, True)
    return None


def _heading_text(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) > 1 and re.fullmatch(r"\d+(?:\.\d+)*\.?|table\s+[\w.\-]+\.?", lines[0], re.I):
        return f"{lines[0]} {lines[1]}"
    return lines[0]


SUBNUMBERED_RE = re.compile(r"^\d+(?:\.\d+)+\.?(?:\s+\S.*)?$")


def _block_heading_lines(block: BlockInput) -> list[tuple[float, str, bool]]:
    """(y, text, is_first_line) heading candidates of a block.

    PyMuPDF sometimes glues a section heading ("5.2 ESD Ratings") to the end of
    the previous footnote block, so sub-numbered lines inside a block count too.
    """
    lines = [line.strip() for line in block.text.strip().splitlines() if line.strip()]
    if not lines:
        return []
    out = [(block.y0, _heading_text(block.text), True)]
    height = max(1.0, block.y1 - block.y0)
    for index in range(1, len(lines)):
        line = lines[index]
        if not SUBNUMBERED_RE.match(line):
            continue
        if re.fullmatch(r"\d+(?:\.\d+)+\.?", line) and index + 1 < len(lines):
            line = f"{line} {lines[index + 1]}"
        out.append((block.y0 + height * index / len(lines), line, False))
    return out


def build_section_events(blocks: list[BlockInput]) -> list[SectionEvent]:
    events: list[SectionEvent] = []
    section: str | None = None
    ordered = sorted(blocks, key=lambda b: (b.page_number, round(b.y0), b.x0))
    for block in ordered:
        for y, line, is_first in _block_heading_lines(block):
            found = _heading_section(line)
            if found is None:
                continue
            kind, new_section, _ = found
            if not is_first and kind == "reset":
                continue
            title = " ".join(line.split())
            if kind == "weak" and (section is None or section == "absolute_maximum"):
                # Generic "... characteristics" titles stay in the current section
                # (e.g. "Voltage characteristics" under Absolute Maximum Ratings).
                events.append(SectionEvent(block.page_number, y, section, title))
                continue
            section = new_section
            events.append(SectionEvent(block.page_number, y, section, title))
    events.sort(key=lambda e: (e.page_number, e.y))
    return events


def _state_at(events: list[SectionEvent], page_number: int, y: float) -> SectionEvent | None:
    current = None
    for event in events:
        if (event.page_number, event.y) <= (page_number, y):
            current = event
        else:
            break
    return current


HEADER_KEYWORDS_RE = re.compile(r"\b(min|typ|max|nom|value)\.?\b", re.I)
UNIT_KEYWORD_RE = re.compile(r"\bunits?\b", re.I)


def candidate_pages(blocks: list[BlockInput], events: list[SectionEvent]) -> list[int]:
    by_page: dict[int, list[str]] = {}
    for block in blocks:
        by_page.setdefault(block.page_number, []).append(block.text)
    pages: list[int] = []
    for page_number in sorted(by_page):
        text = "\n".join(by_page[page_number])
        if not (UNIT_KEYWORD_RE.search(text) and len(HEADER_KEYWORDS_RE.findall(text)) >= 2) and not re.search(
            r"\bmin\.?\b.*\bmax\.?\b", text, re.I | re.S
        ):
            continue
        start = _state_at(events, page_number, -1)
        on_page = [e for e in events if e.page_number == page_number]
        sections = {start.section if start else None} | {e.section for e in on_page}
        if sections - {None}:
            pages.append(page_number)
        if len(pages) >= MAX_CANDIDATE_PAGES:
            break
    return pages


# ---------------------------------------------------------------- parameters

def _r(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


# Matched against the parameter label (descriptive text), first match wins.
PARAMETER_RULES: list[tuple[str, re.Pattern]] = [
    ("esd_hbm", _r(r"human[\s-]+body|\bhbm\b")),
    ("esd_cdm", _r(r"charged[\s-]+device|\bcdm\b")),
    ("esd_mm", _r(r"machine\s+model")),
    ("esd_rating", _r(r"electrostatic\s+discharge|\besd\b")),
    ("thermal_resistance_ja", _r(r"junction[\s-]+to[\s-]+ambient|θ\s*ja|theta\s*ja|\bRthJA\b")),
    ("thermal_resistance_jc", _r(r"junction[\s-]+to[\s-]+case|θ\s*jc|theta\s*jc")),
    ("thermal_resistance_jb", _r(r"junction[\s-]+to[\s-]+board|θ\s*jb")),
    ("thermal_characterization_jt", _r(r"junction[\s-]+to[\s-]+top|ψ\s*jt")),
    ("thermal_characterization_jb", _r(r"ψ\s*jb")),
    ("storage_temperature", _r(r"storage\s+temperature")),
    ("junction_temperature", _r(r"junction\s+temperature")),
    ("soldering_temperature", _r(r"solder|lead\s+temperature")),
    ("operating_temperature", _r(r"(operating|ambient|free[\s-]?air)\s+temperature|^temperature(\s+range)?$")),
    ("input_offset_voltage_drift", _r(r"offset\s+voltage\s+(temperature\s+)?drift|offset\s+voltage\s+temperature\s+coefficient|drift.*offset\s+voltage")),
    ("input_offset_voltage_adjustment", _r(r"offset\s+voltage\s+adjust")),
    ("input_offset_voltage", _r(r"input\s+offset\s+voltage|^offset\s+voltage")),
    ("input_offset_current_drift", _r(r"offset\s+current\s+drift")),
    ("input_offset_current", _r(r"input\s+offset\s+current")),
    ("input_bias_current", _r(r"input\s+bias\s+current|^bias\s+current")),
    ("cmrr", _r(r"common[\s-]+mode\s+rejection|\bcmrr\b")),
    ("psrr", _r(r"(power[\s-]+)?supply[\s-]+(voltage\s+)?rejection|\bpsrr\b|\bksvr\b")),
    ("slew_rate", _r(r"slew\s+rate")),
    ("gain_bandwidth", _r(r"gain[\s-]+bandwidth|unity[\s-]+gain\s+(bandwidth|frequency)|\bgbw\b|^bandwidth$")),
    ("open_loop_gain", _r(r"(open[\s-]+loop|large[\s-]+signal)\s+(voltage\s+)?gain|\baol\b")),
    ("input_voltage_noise", _r(r"voltage\s+noise")),
    ("input_resistance", _r(r"input\s+resistance|input\s+impedance")),
    ("input_capacitance", _r(r"input\s+capacitance")),
    ("common_mode_voltage_range", _r(r"common[\s-]+mode\s+(input\s+)?voltage|^input\s+voltage\s+range")),
    ("differential_input_voltage", _r(r"differential\s+input\s+voltage")),
    ("output_voltage_swing", _r(r"output\s+voltage\s+swing|voltage\s+output\s+swing")),
    ("short_circuit_current", _r(r"short[\s-]+circuit\s+(output\s+)?current")),
    ("short_circuit_duration", _r(r"short[\s-]+circuit\s+duration")),
    ("supply_current", _r(r"supply\s+current|quiescent|current\s+consumption|power\s+supply\s+current")),
    ("power_dissipation", _r(r"power\s+(dissipation|consumption)")),
    ("dropout_voltage", _r(r"dropout\s+voltage")),
    ("line_regulation", _r(r"line\s+regulation")),
    ("load_regulation", _r(r"load\s+regulation")),
    ("efficiency", _r(r"\befficiency\b")),
    ("feedback_voltage", _r(r"feedback\s+voltage")),
    ("adc_sampling_time", _r(r"sampling\s+time")),
    ("reference_voltage", _r(r"reference\s+voltage")),
    ("switching_frequency", _r(r"(oscillator|switching)\s+frequency")),
    ("clock_frequency", _r(r"clock\s+frequency|cpu\s+frequency|operating\s+frequency|maximum\s+frequency|system\s+clock")),
    ("leakage_current", _r(r"leakage\s+current")),
    ("input_low_voltage", _r(r"input\s+low[\s-]+(level\s+)?voltage|low[\s-]+level\s+input\s+voltage")),
    ("input_high_voltage", _r(r"input\s+high[\s-]+(level\s+)?voltage|high[\s-]+level\s+input\s+voltage")),
    ("output_low_voltage", _r(r"output\s+low[\s-]+(level\s+)?voltage|low[\s-]+level\s+output\s+voltage")),
    ("output_high_voltage", _r(r"output\s+high[\s-]+(level\s+)?voltage|high[\s-]+level\s+output\s+voltage")),
    ("propagation_delay", _r(r"propagation\s+delay")),
    ("rise_time", _r(r"rise\s+time")),
    ("fall_time", _r(r"fall\s+time")),
    ("flash_size", _r(r"\bflash\s+(memory\s+)?(size|density)")),
    ("sram_size", _r(r"\bsram\s+(size|density)")),
    ("gpio_count", _r(r"\bgpio\b|number\s+of\s+i/o")),
    ("analog_supply_voltage", _r(r"analog\s+(operating|supply)\s+voltage")),
    ("backup_supply_voltage", _r(r"backup\s+(operating|supply)\s+voltage")),
    ("supply_voltage", _r(r"supply\s+voltage|operating\s+voltage|^supply\s+range")),
    ("output_voltage", _r(r"output\s+voltage")),
    ("input_voltage", _r(r"input\s+voltage|voltage\s+on\s+(any|input)")),
    ("output_current", _r(r"output\s+current|load\s+current|sink\s+current|source\s+current")),
]

# Matched against the symbol column (spaces removed), full match.
SYMBOL_RULES: list[tuple[str, re.Pattern]] = [
    ("supply_voltage", _r(r"V(DD|CC|S|\+|SUPPLY)(-?(VSS|GND))?|V(DD|CC)[-−](VSS|GND)")),
    ("analog_supply_voltage", _r(r"VDDA")),
    ("backup_supply_voltage", _r(r"VBAT")),
    ("supply_current", _r(r"I(DD|CC|Q|S)")),
    ("power_dissipation", _r(r"PD|PTOT")),
    ("junction_temperature", _r(r"TJ(MAX)?")),
    ("storage_temperature", _r(r"TSTG")),
    ("operating_temperature", _r(r"TA|TOPR")),
    ("input_low_voltage", _r(r"VIL")),
    ("input_high_voltage", _r(r"VIH")),
    ("output_low_voltage", _r(r"VOL")),
    ("output_high_voltage", _r(r"VOH")),
    ("clock_frequency", _r(r"f(HCLK|CPU|CLK|MAX|OSC)")),
    ("input_offset_voltage", _r(r"V(IO|OS)")),
    ("input_bias_current", _r(r"I(IB|B)")),
    ("slew_rate", _r(r"SR")),
    ("thermal_resistance_ja", _r(r"R?θJA|RTHJA|ΘJA")),
]

PARAMETER_CATEGORY = {
    "esd_hbm": "electrical",
    "esd_cdm": "electrical",
    "esd_mm": "electrical",
    "slew_rate": "timing",
    "gain_bandwidth": "timing",
    "clock_frequency": "timing",
    "switching_frequency": "timing",
    "propagation_delay": "timing",
    "rise_time": "timing",
    "fall_time": "timing",
    "open_loop_gain": "electrical",
    "cmrr": "electrical",
    "psrr": "electrical",
    "efficiency": "electrical",
    "short_circuit_duration": "electrical",
    "flash_size": "memory",
    "sram_size": "memory",
    "gpio_count": "interface",
}

FOOTNOTE_RE = re.compile(r"\(\d+\)|\[\d+\]|\*+")


KEY_FAMILY = (
    ("temperature", "temperature"),
    ("thermal_resistance", "thermal"),
    ("_voltage", "voltage"),
    ("voltage_", "voltage"),
    ("_current", "current"),
    ("frequency", "frequency"),
    ("bandwidth", "frequency"),
    ("power_dissipation", "power"),
    ("_time", "time"),
    ("propagation_delay", "time"),
    ("slew_rate", "slew"),
)


def _unit_family(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.strip().replace("μ", "µ")
    if re.search(r"°C/W|K/W", u):
        return "thermal"
    if re.search(r"/(µ|u|m|n)?s$", u) and u.startswith(("V", "mV", "kV")):
        return "slew"
    if "/" in u or u in {"%", "dB", "ppm"}:
        return "ratio"
    if re.fullmatch(r"°?C|ºC", u):
        return "temperature"
    m = re.fullmatch(r"[pnuµmkMG]?(V|A|W|Hz|s|Ω)", u)
    if not m:
        return None
    return {"V": "voltage", "A": "current", "W": "power", "Hz": "frequency", "s": "time", "Ω": "resistance"}[m.group(1)]


def _family_ok(key: str, unit: str | None) -> bool:
    actual = _unit_family(unit)
    if actual is None:
        return True
    if re.search(r"drift|rejection|gain|cmrr|psrr|regulation|coefficient|noise", key):
        return True
    for token, family in KEY_FAMILY:
        if token in key:
            return actual == family
    return True


def clean_label(text: str) -> str:
    text = FOOTNOTE_RE.sub(" ", text or "")
    return " ".join(text.split()).strip(" ,;:")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:60] or "parameter"


def canonical_parameter(label: str, symbol: str | None = None, section: str | None = None) -> tuple[str, bool]:
    """Return (canonical key, matched_rule)."""
    label = clean_label(label)
    if section == "esd" and not re.search(r"model|hbm|cdm", label, re.I):
        return "esd_rating", True
    for key, pattern in PARAMETER_RULES:
        if pattern.search(label):
            return key, True
    if symbol:
        compact = re.sub(r"\s+", "", clean_label(symbol))
        for key, pattern in SYMBOL_RULES:
            if pattern.fullmatch(compact):
                return key, True
    if section == "thermal" and re.search(r"θ|thermal", label, re.I):
        return "thermal_resistance", True
    return slugify(label), False


# ---------------------------------------------------------------- values

MINUS_CHARS = str.maketrans({"–": "-", "−": "-", "‒": "-", "﹣": "-"})
NUMBER_TOKEN_RE = re.compile(r"^(?P<pm>±)?(?P<num>[-+]?\d+(?:[.,]\d+)?)(?P<unit>[A-Za-zµμΩ°%/√]+[A-Za-z0-9µμΩ°/√]*)?$")
RANGE_TEXT_RE = re.compile(
    r"^(?P<a>[-+±]?\d+(?:\.\d+)?)\s*(?P<ua>[A-Za-zµμΩ°]*)\s*(?:to|~|\.\.\.?|…)\s*(?P<b>[-+±]?\d+(?:\.\d+)?)\s*(?P<ub>[A-Za-zµμΩ°/%]*)$",
    re.I,
)
RELATIVE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_()]*\s*[+\-]\s*\d+(?:\.\d+)?$")
EMPTY_TOKENS = {"", "-", "—", "–", "−", "n/a", "na", "/"}


@dataclass
class ZoneValue:
    text: str
    number: float | None = None
    unit: str | None = None
    low: float | None = None  # for "a to b" inside one column
    high: float | None = None


def parse_zone(text: str) -> ZoneValue | None:
    raw = " ".join(FOOTNOTE_RE.sub(" ", text or "").split()).strip(" ,;:")
    if raw.lower() in EMPTY_TOKENS:
        return None
    norm = raw.translate(MINUS_CHARS).replace(" ", "") if not re.search(r"\bto\b", raw) else raw.translate(MINUS_CHARS)
    rng = RANGE_TEXT_RE.match(norm.strip())
    if rng:
        a = float(rng.group("a").replace("±", ""))
        b = float(rng.group("b").replace("±", ""))
        unit = rng.group("ub") or rng.group("ua") or None
        return ZoneValue(text=raw, low=min(a, b), high=max(a, b), unit=unit)
    match = NUMBER_TOKEN_RE.match(norm)
    if match:
        number = float(match.group("num").replace(",", "."))
        if match.group("pm"):
            number = abs(number)
        return ZoneValue(text=raw, number=number, unit=match.group("unit"))
    if RELATIVE_RE.match(norm) or re.match(r"^[A-Za-z]{1,6}[+\-]", norm):
        return ZoneValue(text=raw)
    if raw.lower() in {"continuous", "unlimited", "indefinite", "infinite"}:
        return ZoneValue(text=raw)
    return None


# ---------------------------------------------------------------- rows

@dataclass
class ElectricalRow:
    parameter: str
    label: str
    symbol: str | None
    condition: str | None
    condition_type: str
    section: str | None
    min_value: float | None
    typ_value: float | None
    max_value: float | None
    min_text: str | None
    typ_text: str | None
    max_text: str | None
    unit: str | None
    page_number: int
    source_text: str
    bbox: list[float]
    confidence: float
    parser_rule: str
    title: str | None = None

    @property
    def value_text(self) -> str:
        parts = []
        unit = f" {self.unit}" if self.unit else ""
        if self.min_text and self.max_text and not self.typ_text:
            return f"{self.min_text} to {self.max_text}{unit}"
        for name, text in (("min", self.min_text), ("typ", self.typ_text), ("max", self.max_text)):
            if text:
                parts.append(f"{name} {text}")
        if len(parts) == 1 and self.typ_text and self.min_text is None and self.max_text is None:
            return f"{self.typ_text}{unit}"
        return ", ".join(parts) + unit


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _keyword(text: str) -> str | None:
    token = re.sub(r"\(\d+\)|[^A-Za-z]", "", text).upper()
    return {
        "MIN": "min", "MINIMUM": "min", "TYP": "typ", "TYPICAL": "typ", "NOM": "typ", "NOMINAL": "typ",
        "MAX": "max", "MAXIMUM": "max", "UNIT": "unit", "UNITS": "unit", "VALUE": "value", "VALUES": "value",
        "PARAMETER": "param", "PARAMETERS": "param", "CHARACTERISTIC": "param", "CHARACTERISTICS": "param",
        "DESCRIPTION": "param", "RATINGS": "param", "RATING": "param", "ITEM": "param",
        "SYMBOL": "symbol", "CONDITIONS": "cond", "CONDITION": "cond", "TEST": "cond",
    }.get(token)


@dataclass
class Header:
    y: float
    y1: float
    numeric: dict[str, float]  # kind -> x center
    unit_x: float | None
    text_cols: list[tuple[float, float, str]]  # (x0, x1, kind) sorted
    x_min: float
    x_max: float

    @property
    def numeric_sorted(self) -> list[tuple[str, float]]:
        return sorted(self.numeric.items(), key=lambda item: item[1])

    left_override: float | None = None

    def numeric_left(self) -> float:
        if self.left_override is not None:
            return self.left_override
        cols = self.numeric_sorted
        if len(cols) >= 2:
            half = (cols[1][1] - cols[0][1]) / 2
        else:
            half = 22.0
        return cols[0][1] - max(10.0, min(half, 30.0))

    def unit_left(self) -> float | None:
        if self.unit_x is None:
            return None
        last = self.numeric_sorted[-1][1] if self.numeric else None
        if last is None:
            return self.unit_x - 18
        return (last + self.unit_x) / 2

    def zone(self, x: float) -> str:
        unit_left = self.unit_left()
        if unit_left is not None and x >= unit_left:
            return "unit"
        if self.numeric and x >= self.numeric_left():
            return min(self.numeric.items(), key=lambda item: abs(item[1] - x))[0]
        kind = self.text_cols[0][2] if self.text_cols else None
        for index, (x0, _x1, col_kind) in enumerate(self.text_cols):
            boundary = x0 - 4 if index == 0 else (self.text_cols[index - 1][1] + x0) / 2
            if x >= boundary:
                kind = col_kind
        return kind or "text"


def _group_lines(words: list[Word], tolerance: float = 2.6) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.cy, w.x0)):
        if lines and abs(lines[-1][-1].cy - word.cy) <= tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _header_from(line: list[Word]) -> Header | None:
    kinds: dict[str, Word] = {}
    for word in line:
        kind = _keyword(word.text)
        if kind in {"min", "typ", "max"} and kind in kinds:
            return None  # repeated MIN/MAX groups (per-supply sub-tables): not parsed
        if kind and kind not in kinds:
            kinds[kind] = word
    numeric = {k: w.cx for k, w in kinds.items() if k in {"min", "typ", "max", "value"}}
    if "value" in numeric and len(numeric) > 1:
        numeric.pop("value")
    has_unit = "unit" in kinds
    if not ((numeric and has_unit) or ("min" in numeric and "max" in numeric)):
        return None
    if len(line) > 16:  # prose, not a header
        return None
    text_cols = sorted((w.x0, w.x1, k) for k, w in kinds.items() if k in {"param", "symbol", "cond"})
    return Header(
        y=min(w.y0 for w in line),
        y1=max(w.y1 for w in line),
        numeric=numeric,
        unit_x=kinds["unit"].cx if has_unit else None,
        text_cols=text_cols,
        x_min=min(w.x0 for w in line),
        x_max=max(w.x1 for w in line),
    )


def find_header_lines(lines: list[list[Word]]) -> list[Header]:
    """Header lines, allowing a header split over two close lines ("Max(1)" above "Symbol ... Unit")."""
    headers: list[Header] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        header = _header_from(line)
        if header is None and index + 1 < len(lines) and any(_keyword(w.text) for w in line):
            nxt = lines[index + 1]
            if 0 < nxt[0].cy - line[0].cy <= 16 and any(_keyword(w.text) for w in nxt):
                header = _header_from(line + nxt)
                if header is not None:
                    index += 1
        if header is not None:
            headers.append(header)
        index += 1
    return headers


def _subcolumns(header: Header, words: list[Word]) -> tuple[dict[str, list[tuple[float, str]]], float]:
    """Sub-column labels under a numeric header (e.g. "TA = 85 °C | TA = 105 °C" under Max).

    Returns ({zone: [(x_center, label)]}, y_bottom_of_subheader) and widens the
    header's numeric area to cover the sub-columns.
    """
    if not header.numeric:
        return {}, header.y1
    centers = header.numeric_sorted
    left_limit = centers[0][1] - 75
    unit_left = header.unit_left() or 1e9
    result: dict[str, list[tuple[float, str]]] = {}
    bottom = header.y1
    lines = _group_lines([w for w in words if header.y1 < w.cy <= header.y1 + 26])
    min_x = None
    for line in lines:
        area = [w for w in line if left_limit <= w.cx < unit_left]
        if not area or not any(re.search(r"[=°]", w.text) for w in area):
            break
        clusters: list[list[Word]] = []
        for word in sorted(area, key=lambda w: w.x0):
            if clusters and word.x0 - clusters[-1][-1].x1 < 9:
                clusters[-1].append(word)
            else:
                clusters.append([word])
        for cluster in clusters:
            cx = (cluster[0].x0 + cluster[-1].x1) / 2
            kind = min(centers, key=lambda item: abs(item[1] - cx))[0]
            result.setdefault(kind, []).append((cx, " ".join(w.text for w in cluster)))
            min_x = cluster[0].x0 if min_x is None else min(min_x, cluster[0].x0)
        bottom = max(w.y1 for w in line)
    result = {k: v for k, v in result.items() if len(v) >= 2}
    if result and min_x is not None:
        header.left_override = min(header.numeric_left(), min_x - 4)
    else:
        bottom = header.y1
    return result, bottom


@dataclass
class Cell:
    x0: float
    y0: float
    x1: float
    y1: float
    words: list[Word] = field(default_factory=list)
    col: int = 0

    def contains_y(self, y: float) -> bool:
        return self.y0 - 1 <= y <= self.y1 + 1

    @property
    def text(self) -> str:
        return " ".join(w.text for line in _group_lines(self.words) for w in line)


def _assign_words(cells: list[Cell], words: list[Word]) -> None:
    for word in words:
        for cell in cells:
            if cell.x0 - 1 <= word.cx <= cell.x1 + 1 and cell.y0 - 1 <= word.cy <= cell.y1 + 1:
                cell.words.append(word)
                break


@dataclass
class _Context:
    page_number: int
    condition_type: str
    section: str | None
    title: str | None


def _make_row(
    ctx: _Context,
    header: Header,
    label: str,
    symbol: str | None,
    condition: str | None,
    zones: dict[str, str],
    unit_text: str | None,
    words: list[Word],
    rule: str,
    base_conf: float,
    variant: str | None,
) -> ElectricalRow | None:
    label = clean_label(label)
    if not label or len(label) > 160 or not re.search(r"[A-Za-z]{2,}", label):
        return None
    values: dict[str, ZoneValue] = {}
    for kind, text in zones.items():
        parsed = parse_zone(text)
        if parsed is not None:
            values[kind] = parsed
    if not values:
        return None
    if all(v.number is None and v.low is None for v in values.values()) and len(values) > 1:
        return None
    unit = clean_label(unit_text or "") or None
    if unit and (len(unit) > 14 or re.search(r"\d{2,}", unit)):
        unit = None
    if unit is None:
        unit = next((v.unit for v in values.values() if v.unit), None)

    mn = mx = ty = None
    mn_t = mx_t = ty_t = None
    for kind, value in values.items():
        if value.low is not None:
            mn, mx, mn_t, mx_t = value.low, value.high, value.text.split("to")[0].strip(), value.text.split("to")[-1].strip()
            continue
        if kind == "min":
            mn, mn_t = value.number, value.text
        elif kind == "max":
            mx, mx_t = value.number, value.text
        elif kind == "typ":
            ty, ty_t = value.number, value.text
        else:  # "value" column: an absolute-maximum single value is a maximum
            if ctx.condition_type == "absolute_maximum" and ctx.section != "esd":
                mx, mx_t = value.number, value.text
            else:
                ty, ty_t = value.number, value.text
    if not symbol:
        # TI tables put the symbol in front of the name: "VOS Input offset voltage".
        lead = re.match(r"^([A-Za-z][A-Za-z0-9()/_+\-]{0,9})\s+([A-Z][a-z].*)$", label)
        if lead and sum(c.isupper() for c in lead.group(1)) >= 2:
            symbol, label = lead.group(1), lead.group(2)
    key, matched = canonical_parameter(label, symbol, ctx.section)
    if not matched and (
        len(label.split()) > 10 or re.search(r"\b(the|is|are|have|has|doesn|which|when|must)\b", label, re.I)
    ):
        return None  # footnote / prose captured in a cell, not a parameter name
    if key == "operating_temperature" and re.fullmatch(r"temperature( range)?", label, re.I) and condition:
        for cond_key in ("junction_temperature", "storage_temperature"):
            if re.search(r"junction|\bT\s*J\b" if cond_key == "junction_temperature" else r"storage|stg", condition, re.I):
                key = cond_key
                break
    if (ctx.section == "esd" or key == "esd_rating") and condition:
        esd_key, esd_matched = canonical_parameter(condition, None, None)
        if esd_matched and esd_key.startswith("esd_") and esd_key != "esd_rating":
            key = esd_key
    if matched and not _family_ok(key, unit):
        key, matched = slugify(label), False
    if ctx.section == "thermal" and key == slugify(label) and not matched:
        return None
    confidence = base_conf
    if not matched:
        confidence -= 0.1
    if unit is None:
        confidence -= 0.1
    if all(v is None for v in (mn, ty, mx)):
        confidence -= 0.2
    cond_clean = clean_label(condition or "")
    if cond_clean.lower() in EMPTY_TOKENS:
        cond_clean = ""
    cond_parts = [c for c in (cond_clean, f"[{variant}]" if variant else "") if c]
    xs = [w.x0 for w in words] + [w.x1 for w in words]
    ys = [w.y0 for w in words] + [w.y1 for w in words]
    source_text = " ".join(
        part for part in (symbol or "", label, clean_label(condition or ""), " ".join(v.text for v in values.values()), unit or "") if part
    )
    return ElectricalRow(
        parameter=key,
        label=label,
        symbol=clean_label(symbol or "") or None,
        condition=" ".join(cond_parts) or None,
        condition_type="general" if key.startswith("esd_") else ctx.condition_type,
        section=ctx.title or ctx.section,
        min_value=mn,
        typ_value=ty,
        max_value=mx,
        min_text=mn_t,
        typ_text=ty_t,
        max_text=mx_t,
        unit=unit,
        page_number=ctx.page_number,
        source_text=source_text[:400],
        bbox=[round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)] if xs else [0, 0, 0, 0],
        confidence=round(max(0.2, min(0.95, confidence)), 2),
        parser_rule=rule,
    )


def _cell_kind(header: Header, cell: Cell, first_col: int) -> str:
    center = (cell.x0 + cell.x1) / 2
    zone = header.zone(center)
    if zone == "unit":
        return "unit"
    if zone in {"min", "typ", "max", "value"}:
        # A wide cell starting in the text area (merged across columns) stays text.
        if header.zone(cell.x0 + 6) in {"min", "typ", "max", "value", "unit"}:
            return "numeric"
        zone = header.zone(cell.x0 + 6)
    if header.text_cols:
        return zone if zone in {"param", "symbol", "cond"} else "param"
    return "param" if cell.col == first_col else "cond"


def _join_fragments(words: list[Word], header: Header) -> list[Word]:
    """Glue a wrapped relative limit ("VDD+" above "0.3") into one word."""
    result = sorted(words, key=lambda w: (w.cy, w.x0))
    used: set[int] = set()
    out: list[Word] = []
    for index, word in enumerate(result):
        if index in used:
            continue
        same_line_right = any(
            abs(o.cy - word.cy) < 2 and o.x0 > word.x0 and header.zone(o.cx) == header.zone(word.cx)
            for o in result
            if o is not word
        )
        if re.search(r"[+\-–−]$", word.text) and not same_line_right:
            for other_index in range(index + 1, len(result)):
                other = result[other_index]
                if other_index in used or not (0 < other.cy - word.cy < 14):
                    continue
                if header.zone(other.cx) == header.zone(word.cx) and abs(other.cx - word.cx) < 25:
                    used.add(other_index)
                    word = Word(min(word.x0, other.x0), word.y0, max(word.x1, other.x1), other.y1, word.text + other.text)
                    break
        out.append(word)
    return out


def _join(words: list[Word]) -> str:
    return " ".join(w.text for line in _group_lines(words) for w in line)


def parse_table(
    ctx: _Context,
    header: Header,
    table_cells: list[Cell],
    words: list[Word],
    table_bbox: tuple[float, float, float, float],
    variant: str | None,
) -> list[ElectricalRow]:
    """Parse one find_tables table using header x positions for numeric columns.

    Numbers come from visual lines (assigned to MIN/TYP/MAX/VALUE by x);
    parameter / symbol / condition / unit come from the table cells whose
    vertical span covers that line, so merged cells apply to every sub-row.
    """
    body_words = [
        w for w in words
        if w.cy > header.y1 + 1 and table_bbox[0] - 2 <= w.cx <= table_bbox[2] + 2 and w.cy <= table_bbox[3] + 2
    ]
    body_cells = [c for c in table_cells if c.y1 > header.y1 + 1]
    _assign_words(body_cells, body_words)
    cols = sorted({c.col for c in body_cells})
    first_col = cols[0] if cols else 0
    kinds = {id(cell): _cell_kind(header, cell, first_col) for cell in body_cells}

    subcols, sub_bottom = _subcolumns(header, body_words)
    numeric_words = [
        w for w in body_words if header.zone(w.cx) in {"min", "typ", "max", "value"} and w.cy > sub_bottom + 0.5
    ]

    def _is_number(word: Word) -> bool:
        parsed = parse_zone(word.text)
        return bool(parsed and (parsed.number is not None or parsed.low is not None))

    numeric_words = _join_fragments(numeric_words, header)
    merged: list[list[Word]] = []
    pending: list[Word] = []
    for line in _group_lines(numeric_words, tolerance=2.0):
        if any(_is_number(w) for w in line):
            merged.append(pending + line)  # a wrapped fragment ("VDD+") joins the line below
            pending = []
        elif all(re.search(r"[+\-–−]$", w.text) for w in line):
            pending.extend(line)
        else:
            merged.append(line)  # textual value such as "Continuous"
    if pending and merged and pending[0].cy - merged[-1][-1].cy < 12:
        merged[-1].extend(pending)
    elif pending:
        merged.append(pending)

    def _row_y(line: list[Word]) -> float:
        ys = sorted(w.cy for w in line if _is_number(w)) or [line[0].cy]
        return ys[len(ys) // 2]

    row_ys = [_row_y(line) for line in merged]

    def _cell_words_for(cell: Cell, y: float) -> list[Word]:
        """A text cell spanning N sub-rows with exactly N lines: keep the line of this sub-row."""
        covered = [ry for ry in row_ys if cell.contains_y(ry)]
        lines = _group_lines(cell.words)
        if len(covered) >= 2 and len(lines) == len(covered):
            return min(lines, key=lambda ln: abs(ln[0].cy - y))
        return cell.words

    rows: list[ElectricalRow] = []
    for line in merged:
        y = _row_y(line)
        zones: dict[str, list[Word]] = {}
        for word in line:
            zones.setdefault(header.zone(word.cx), []).append(word)
        variants_zone_text = _split_subcolumns(zones, subcols)
        param_w: list[Word] = []
        symbol_w: list[Word] = []
        cond_w: list[Word] = []
        unit_w: list[Word] = []
        for cell in body_cells:
            if not cell.words or not cell.contains_y(y):
                continue
            kind = kinds[id(cell)]
            for word in _cell_words_for(cell, y) if kind == "cond" else cell.words:
                word_zone = header.zone(word.cx)
                if word_zone == "unit":
                    unit_w.append(word)
                elif word_zone in {"min", "typ", "max", "value"} or kind == "numeric":
                    continue
                elif kind == "symbol":
                    symbol_w.append(word)
                elif kind == "cond":
                    cond_w.append(word)
                else:
                    param_w.append(word)
        label = _join(param_w)
        unit = None
        if unit_w:
            unit_lines = _group_lines(unit_w)
            unit = " ".join(w.text for w in min(unit_lines, key=lambda ln: abs(ln[0].cy - y)))
        if not label and rows:
            label = rows[-1].label
        if unit is None and rows and rows[-1].label == label:
            unit = rows[-1].unit
        for extra_cond, zone_text in variants_zone_text:
            cond_text = " ".join(part for part in (_join(cond_w), extra_cond) if part)
            row = _make_row(
                ctx,
                header,
                label,
                _join(symbol_w) or None,
                cond_text or None,
                zone_text,
                unit,
                param_w + symbol_w + cond_w + line,
                "electrical_table",
                0.88,
                variant,
            )
            if row is not None:
                rows.append(row)
    return rows


def _split_subcolumns(
    zones: dict[str, list[Word]], subcols: dict[str, list[tuple[float, str]]]
) -> list[tuple[str, dict[str, str]]]:
    """One zone-text mapping per sub-column when a zone holds several numbers."""

    def _text(words: list[Word]) -> str:
        return " ".join(w.text for w in sorted(words, key=lambda w: (round(w.cy), w.x0)))

    base = {k: _text(v) for k, v in zones.items()}
    for zone, columns in subcols.items():
        words = zones.get(zone) or []
        if len(words) < 2:
            continue
        buckets: dict[int, list[Word]] = {}
        for word in words:
            nearest = min(range(len(columns)), key=lambda i: abs(columns[i][0] - word.cx))
            buckets.setdefault(nearest, []).append(word)
        result = []
        for index, bucket in sorted(buckets.items()):
            mapping = dict(base)
            mapping[zone] = _text(bucket)
            result.append((columns[index][1], mapping))
        return result
    return [("", base)]


SECTION_END_RE = re.compile(r"^(\(\d+\)|notes?:|table\s+\d|figure\s+\d|\d+(\.\d+)+\s+[A-Z])", re.I)


def parse_lines(
    ctx: _Context,
    header: Header,
    lines: list[list[Word]],
    variant: str | None,
) -> list[ElectricalRow]:
    """Fallback: aligned text lines under a header (no table grid found)."""
    rows: list[ElectricalRow] = []
    last_label = ""
    last_unit: str | None = None
    pending_label: list[str] = []
    previous_y = header.y1
    for line in lines:
        if line[0].cy <= header.y1 + 1:
            continue
        if line[0].cy - previous_y > 40:
            break
        text = " ".join(w.text for w in line)
        if SECTION_END_RE.match(text) or find_header_lines([line]):
            break
        previous_y = line[-1].cy
        zones: dict[str, list[Word]] = {}
        for word in line:
            zones.setdefault(header.zone(word.cx), []).append(word)
        numeric = {k: " ".join(w.text for w in v) for k, v in zones.items() if k in {"min", "typ", "max", "value"}}
        texts = {k: " ".join(w.text for w in v) for k, v in zones.items() if k not in {"min", "typ", "max", "value", "unit"}}
        unit = " ".join(w.text for w in zones.get("unit", [])) or None
        if not numeric:
            if texts:
                pending_label.append(texts.get("param") or texts.get("text") or " ".join(texts.values()))
            continue
        label = texts.get("param") or texts.get("text") or ""
        if pending_label and not label:
            label = " ".join(pending_label)
        elif pending_label and label and len(pending_label) == 1 and not label[:1].isupper():
            label = pending_label[0] + " " + label
        pending_label = []
        if not label:
            label = last_label
        if unit is None and label == last_label:
            unit = last_unit
        row = _make_row(
            ctx, header, label, texts.get("symbol"), texts.get("cond"), numeric, unit, line, "electrical_text_lines", 0.72, variant
        )
        if row is not None:
            rows.append(row)
            last_label, last_unit = row.label, row.unit
    return rows


def _variant_for(title: str | None, reference: str | None) -> tuple[str | None, bool]:
    """Return (variant label, keep) for a table title naming device variants."""
    if not title:
        return None, True
    tokens = [t for t in VARIANT_TOKEN_RE.findall(title) if not re.match(r"^(TA|VCC|VDD|ESD|HBM|CDM)", t, re.I)]
    if not tokens:
        return None, True
    variant = ", ".join(dict.fromkeys(tokens))
    if not reference:
        return variant, True
    ref = re.sub(r"[^A-Z0-9]", "", reference.upper())
    title_norm = re.sub(r"[^A-Z0-9]", "", title.upper())
    if ref and ref in title_norm:
        return variant, True
    if any(ref.startswith(re.sub(r"[^A-Z0-9]", "", t.upper())) or re.sub(r"[^A-Z0-9]", "", t.upper()).startswith(ref) for t in tokens):
        return variant, True
    digits = max(re.findall(r"\d+", ref), key=len, default="")
    if digits and len(digits) >= 3 and digits in title_norm:
        return variant, True
    return variant, False


def extract_electrical_rows(
    pdf_path: str | Path,
    blocks: list[BlockInput],
    reference: str | None = None,
) -> list[ElectricalRow]:
    import fitz

    from ..extraction.extractor import _PYMUPDF_LOCK

    events = build_section_events(blocks)
    pages = candidate_pages(blocks, events)
    rows: list[ElectricalRow] = extract_feature_specs(blocks) + extract_dot_leader_ratings(blocks, events)
    if not pages:
        return _dedupe(rows)
    with _PYMUPDF_LOCK:
        doc = fitz.open(str(pdf_path))
        try:
            for page_number in pages:
                if len(rows) >= MAX_ROWS:
                    break
                page = doc[page_number - 1]
                words = [Word(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
                lines = _group_lines(words)
                headers = find_header_lines(lines)
                if not headers:
                    continue
                handled: list[Header] = []
                try:
                    tables = page.find_tables().tables
                except Exception:
                    tables = []
                for tab in tables:
                    x0, y0, x1, y1 = tab.bbox
                    header = next((h for h in headers if y0 - 30 <= h.y <= y1 and h.x_max >= x0 and h.x_min <= x1), None)
                    if header is None or header in handled:
                        continue
                    state = _state_at(events, page_number, y0)
                    if state is None or state.section is None:
                        continue
                    variant, keep = _variant_for(state.title, reference)
                    handled.append(header)
                    if not keep:
                        continue
                    cells: list[Cell] = []
                    seen: set[tuple] = set()
                    for row in tab.rows:
                        for col, bbox in enumerate(row.cells):
                            if bbox is None:
                                continue
                            key = tuple(round(v, 1) for v in bbox)
                            if key in seen:
                                continue
                            seen.add(key)
                            cells.append(Cell(bbox[0], bbox[1], bbox[2], bbox[3], col=col))
                    ctx = _Context(page_number, SECTION_TO_CONDITION[state.section], state.section, state.title)
                    rows.extend(parse_table(ctx, header, cells, words, (x0, y0, x1, y1), variant))
                for header in headers:
                    if header in handled:
                        continue
                    state = _state_at(events, page_number, header.y)
                    if state is None or state.section is None:
                        continue
                    variant, keep = _variant_for(state.title, reference)
                    if not keep:
                        continue
                    ctx = _Context(page_number, SECTION_TO_CONDITION[state.section], state.section, state.title)
                    rows.extend(parse_lines(ctx, header, lines, variant))
        finally:
            doc.close()
    return _dedupe(rows)


def _dedupe(rows: list[ElectricalRow]) -> list[ElectricalRow]:
    seen: set[tuple] = set()
    result: list[ElectricalRow] = []
    for row in rows:
        key = (row.parameter, row.condition_type, row.condition, row.min_value, row.typ_value, row.max_value, row.unit, row.page_number)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


# ---------------------------------------------------------------- dot-leader ratings

DOT_LEADER_RE = re.compile(r"^(?P<label>[A-Za-z][^.…]{2,90}?)\s*(?:\.\s*){3,}\s*(?P<value>.+)$")
DOT_VALUE_RE = re.compile(
    r"^(?P<a>[-+−–±]?\d+(?:\.\d+)?)\s*(?P<ua>°?\s*[A-Za-zµμΩ]*)\s*(?:to|-|–)\s*(?P<b>[+−–-]?\s*\d+(?:\.\d+)?)\s*(?P<ub>°?\s*[A-Za-zµμΩ]+)$"
    r"|^(?P<single>[-+−–±]?\d+(?:\.\d+)?)\s*(?P<us>°?\s*[A-Za-zµμΩ]+)$"
)


def extract_dot_leader_ratings(blocks: list[BlockInput], events: list[SectionEvent]) -> list[ElectricalRow]:
    """"Operating Temperature ........ -55°C to +125°C" lists (Microchip/Atmel style)."""
    rows: list[ElectricalRow] = []
    abs_pages = {e.page_number for e in events if e.section == "absolute_maximum"}
    for block in blocks:
        if block.page_number not in abs_pages:
            continue
        state = _state_at(events, block.page_number, block.y0)
        if state is None or state.section != "absolute_maximum":
            continue
        for raw_line in block.text.splitlines():
            line = " ".join(raw_line.split())
            match = DOT_LEADER_RE.match(line)
            if not match:
                continue
            value = match.group("value").translate(MINUS_CHARS).strip()
            vm = DOT_VALUE_RE.match(value)
            if not vm:
                continue
            label = clean_label(match.group("label"))
            if vm.group("single"):
                low, high = None, float(vm.group("single").replace("±", "").replace(" ", ""))
                unit = vm.group("us").replace(" ", "")
            else:
                low = float(vm.group("a").replace("±", ""))
                high = float(vm.group("b").replace(" ", ""))
                unit = vm.group("ub").replace(" ", "")
            if unit.upper() in {"C", "°C"}:
                unit = "°C"
            key, matched = canonical_parameter(label)
            if matched and not _family_ok(key, unit):
                key, matched = slugify(label), False
            rows.append(
                ElectricalRow(
                    parameter=key,
                    label=label,
                    symbol=None,
                    condition=None,
                    condition_type="absolute_maximum",
                    section=state.title,
                    min_value=low,
                    typ_value=None,
                    max_value=high,
                    min_text=None if low is None else str(vm.group("a")).strip(),
                    typ_text=None,
                    max_text=str(vm.group("b") or vm.group("single")).strip(),
                    unit=unit or None,
                    page_number=block.page_number,
                    source_text=line[:400],
                    bbox=[block.x0, block.y0, block.x1, block.y1],
                    confidence=0.8 if matched else 0.7,
                    parser_rule="electrical_dot_leader",
                )
            )
    return rows


# ---------------------------------------------------------------- feature bullets (first pages)

FEATURE_RULES: list[tuple[str, re.Pattern, str]] = [
    # (parameter, pattern, kind) kind: range|max|value
    ("supply_voltage", re.compile(r"(?:operating|supply)\s+voltage\s*(?:range)?(?:[:\s]|[–-](?=\s))*(?P<a>\d+(?:\.\d+)?)\s*V?\s*(?:to|-|–)\s*(?P<b>\d+(?:\.\d+)?)\s*V\b", re.I), "range"),
    ("supply_voltage", re.compile(r"(?P<a>\d+(?:\.\d+)?)\s*V?\s*(?:to|-|–)\s*(?P<b>\d+(?:\.\d+)?)\s*V\s+(?:application\s+)?(?:supply|operating)", re.I), "range"),
    ("supply_voltage", re.compile(r"(?:wide\s+)?supply\s+range\s*[:\-–]?\s*(?P<a>\d+(?:\.\d+)?)\s*V?\s*(?:to|-|–)\s*(?P<b>\d+(?:\.\d+)?)\s*V\b", re.I), "range"),
    ("operating_temperature", re.compile(r"(?:operating\s+)?temperature\s+range(?:[:\s]|[–-](?=\s))*(?P<a>[-–−]?\d+)\s*°\s*C\s*to\s*\+?(?P<b>\d+)\s*°\s*C", re.I), "range"),
    ("clock_frequency", re.compile(r"(?P<v>\d+(?:\.\d+)?)\s*MHz\s+max(?:imum)?\s+frequency", re.I), "max"),
    ("clock_frequency", re.compile(r"up\s+to\s+(?P<v>\d+(?:\.\d+)?)\s*MHz", re.I), "max"),
    ("flash_size", re.compile(r"(?P<v>\d+)\s*K\s*bytes?\s+(?:of\s+)?(?:in-system\s+self-programmable\s+)?flash", re.I), "value"),
    ("sram_size", re.compile(r"(?P<v>\d+)\s*K\s*bytes?\s+(?:of\s+)?(?:internal\s+)?sram", re.I), "value"),
    ("eeprom_size", re.compile(r"(?P<v>\d+)\s*(?:K\s*)?bytes?\s+eeprom", re.I), "value"),
    ("gpio_count", re.compile(r"(?:up\s+to\s+)?(?P<v>\d+)\s+(?:fast\s+|programmable\s+)?i/o(?:s|\s+lines|\s+ports)?\b", re.I), "value"),
]


def extract_feature_specs(blocks: list[BlockInput], max_page: int = 2) -> list[ElectricalRow]:
    """Headline specs from the first-page feature list (MCU style)."""
    rows: list[ElectricalRow] = []
    seen: set[str] = set()
    pages: dict[int, list[BlockInput]] = {}
    for b in blocks:
        if b.page_number <= max_page:
            pages.setdefault(b.page_number, []).append(b)
    merged_blocks = [
        BlockInput(
            id=0,
            page_number=page,
            text="\n".join(b.text for b in sorted(items, key=lambda b: (b.x0 > 300, b.y0))),
            x0=min(b.x0 for b in items),
            y0=min(b.y0 for b in items),
            x1=max(b.x1 for b in items),
            y1=max(b.y1 for b in items),
        )
        for page, items in sorted(pages.items())
    ]
    for block in merged_blocks:
        text = " ".join(re.sub(r"[\u0300-\u036f\ue000-\uf8ff•▪■]", " ", block.text).split())
        speed = re.search(r"speed\s+grade", text, re.I)
        if speed and "clock_frequency" not in seen:
            window = text[speed.start() : speed.start() + 260]
            grades = [(m, float(m.group(1))) for m in re.finditer(r"\b0\s*[-–]\s*(\d+(?:\.\d+)?)\s*MHz", window)]
            if grades:
                best, number = max(grades, key=lambda item: item[1])
                seen.add("clock_frequency")
                rows.append(
                    ElectricalRow(
                        parameter="clock_frequency", label="Clock frequency", symbol=None, condition="Speed grade",
                        condition_type="general", section="Features", min_value=None, typ_value=None, max_value=number,
                        min_text=None, typ_text=None, max_text=best.group(1), unit="MHz", page_number=block.page_number,
                        source_text=window[:300], bbox=[block.x0, block.y0, block.x1, block.y1], confidence=0.7,
                        parser_rule="feature_list_regex",
                    )
                )
        for key, pattern, kind in FEATURE_RULES:
            if key in seen:
                continue
            match = pattern.search(text)
            if not match:
                continue
            start = max(0, match.start() - 40)
            source = text[start : match.end() + 40]
            if kind == "range":
                low, high = float(match.group("a").translate(MINUS_CHARS)), float(match.group("b"))
                if low >= high:
                    continue
                values = dict(min_value=low, max_value=high, min_text=match.group("a"), max_text=match.group("b"), typ_value=None, typ_text=None)
                unit = "°C" if key == "operating_temperature" else "V"
            elif re.search(r"\d+\s*(?:K\s*(?:bytes?)?\s*)?(?:or|/|,)\s*$", text[: match.start()]):
                # "64 or 128 Kbytes of Flash": the device variant decides; keep the text only.
                lead = re.search(r"(\d+)\s*(?:K\s*(?:bytes?)?\s*)?(?:or|/|,)\s*$", text[: match.start()])
                seen.add(key)
                rows.append(
                    ElectricalRow(
                        parameter=key, label=key.replace("_", " ").capitalize(), symbol=None,
                        condition="Features list (depends on variant)", condition_type="general", section="Features",
                        min_value=None, typ_value=None, max_value=None, min_text=None,
                        typ_text=f"{lead.group(1)} or {match.group('v')}", max_text=None,
                        unit="KB" if key in {"flash_size", "sram_size"} else None, page_number=block.page_number,
                        source_text=text[max(0, lead.start() - 30) : match.end() + 30],
                        bbox=[block.x0, block.y0, block.x1, block.y1], confidence=0.6, parser_rule="feature_list_regex",
                    )
                )
                continue
            else:
                number = float(match.group("v"))
                unit = {"clock_frequency": "MHz", "flash_size": "KB", "sram_size": "KB", "eeprom_size": "B", "gpio_count": None}[key]
                if key == "eeprom_size" and re.search(r"K\s*bytes?\s+eeprom", match.group(0), re.I):
                    unit = "KB"
                if kind == "max":
                    values = dict(max_value=number, max_text=match.group("v"), min_value=None, min_text=None, typ_value=None, typ_text=None)
                else:
                    values = dict(typ_value=number, typ_text=match.group("v"), min_value=None, min_text=None, max_value=None, max_text=None)
            seen.add(key)
            rows.append(
                ElectricalRow(
                    parameter=key,
                    label=key.replace("_", " ").capitalize(),
                    symbol=None,
                    condition="Features list",
                    condition_type="general",
                    section="Features",
                    unit=unit,
                    page_number=block.page_number,
                    source_text=source,
                    bbox=[block.x0, block.y0, block.x1, block.y1],
                    confidence=0.7,
                    parser_rule="feature_list_regex",
                    **values,
                )
            )
    return rows
