"""Scaffolding helpers for adding new corpus cases."""

from __future__ import annotations

import json
from pathlib import Path


CASE_JSON_TEMPLATE = {
    "name": "{{case_name}}",
    "vendor": "",
    "component_type": "",
    "required_fields": [
        "must_have.manufacturer",
        "must_have.base_part",
        "must_have.orderable_parts",
    ],
    "optional_fields": [
        "document.document_title",
        "must_have.rohs",
        "must_have.operating_temperature_range",
    ],
    "allowed_adapters": [
        "generic",
    ],
    "notes": "Fill in corpus metadata for this case.",
}

GOLDEN_JSON_TEMPLATE = {
    "document": {
        "source_file": "input.pdf",
    },
    "must_have": {
        "manufacturer": None,
        "base_part": None,
        "orderable_parts": [],
    },
    "nice_to_have": {},
}

NOTES_TEMPLATE = """# {{case_name}}

Source:
- vendor:
- datasheet URL:
- retrieval date:

Status:
- pdf_added: no
- golden_complete: no
- ready_for_eval: no

Notes:
- Add `input.pdf`.
- Replace placeholder values in `golden.json`.
- Update `case.json` with vendor and expected fields.
"""


def scaffold_case(cases_root: str | Path, case_name: str) -> Path:
    """Create a repeatable case skeleton without fabricating golden values."""

    cases_root = Path(cases_root)
    case_dir = cases_root / case_name
    case_dir.mkdir(parents=True, exist_ok=False)

    case_json = json.dumps(_replace_case_name(CASE_JSON_TEMPLATE, case_name), indent=2) + "\n"
    golden_json = json.dumps(GOLDEN_JSON_TEMPLATE, indent=2) + "\n"
    notes_md = NOTES_TEMPLATE.replace("{{case_name}}", case_name)

    (case_dir / "case.json").write_text(case_json)
    (case_dir / "golden.json").write_text(golden_json)
    (case_dir / "notes.md").write_text(notes_md)
    (case_dir / "input.pdf.placeholder").write_text("Replace this file with the real source PDF named input.pdf.\n")
    return case_dir


def _replace_case_name(payload: dict, case_name: str) -> dict:
    rendered = json.loads(json.dumps(payload))
    rendered["name"] = case_name
    return rendered
