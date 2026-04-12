# Corpus Cases

Each real datasheet case lives under `tests/cases/<case_name>/` and must contain:

- `input.pdf`
- `golden.json`
- `case.json`
- optional `notes.md`

This repository currently contains one real seeded case and supports scaling to a 10-15 case corpus without changing parser code.

Useful commands:

```bash
python3 tools/scaffold_case.py <case_name>
python3 tools/eval_cases.py --validate-only
python3 tools/eval_cases.py --list-cases
python3 tools/eval_cases.py --case sn74lvc1g125
python3 tools/eval_cases.py
```

Templates for new cases live under `tests/templates/case_template/`.
