from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class AIServiceError(Exception):
    public_message = "The local AI service is unavailable."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(detail or self.public_message)


class AIConfigurationError(AIServiceError):
    public_message = "The local AI service is not configured correctly."


class AIOllamaUnavailableError(AIServiceError):
    public_message = "Ollama is not reachable on this computer."


class AIModelMissingError(AIServiceError):
    public_message = "The required local model is not installed."


class AIResponseError(AIServiceError):
    public_message = "The local model returned an invalid or incomplete response."


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        parts.append(value)
                        break
        return "\n".join(parts)
    return str(content)


def extract_json_object(text: str) -> str:
    candidates = [text.strip()]
    fenced_start = text.find("```")
    while fenced_start != -1:
        fenced_end = text.find("```", fenced_start + 3)
        if fenced_end == -1:
            break
        block = text[fenced_start + 3 : fenced_end]
        if block.lower().startswith("json"):
            block = block[4:]
        candidates.append(block.strip())
        fenced_start = text.find("```", fenced_end + 3)

    for candidate in candidates:
        start = candidate.find("{")
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(candidate)):
            char = candidate[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return candidate[start : index + 1]

    raise AIResponseError("No complete JSON object found in model output.")


def parse_model_json(text: str, schema: type[T]) -> T:
    raw = extract_json_object(text)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"Invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AIResponseError("Model output was not a JSON object.")
    try:
        return schema.model_validate(value)
    except ValidationError as exc:
        raise AIResponseError(f"Schema validation failed: {exc}") from exc


def structured_prompt(instruction: str, schema: type[BaseModel]) -> str:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return (
        f"{instruction.strip()}\n"
        "Return only valid JSON matching this schema. Do not include markdown or commentary.\n"
        f"JSON schema:\n{schema_json}"
    )
