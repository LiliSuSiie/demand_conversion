from __future__ import annotations

from typing import Any


def model_to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def extract_text_from_content(content: Any) -> str:
    content = model_to_dict(content)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [extract_text_from_content(item) for item in content]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        text_value = content.get("text")
        if isinstance(text_value, str):
            return text_value.strip()
        if isinstance(text_value, dict):
            nested_text = text_value.get("value") or text_value.get("text") or text_value.get("content")
            if isinstance(nested_text, str):
                return nested_text.strip()
        nested_content = content.get("content")
        if nested_content is not None:
            return extract_text_from_content(nested_content)
    return ""


def extract_text_from_payload(payload: Any) -> tuple[str, str]:
    payload = model_to_dict(payload)
    if not isinstance(payload, dict):
        return "", "empty"

    output_text = extract_text_from_content(payload.get("output_text"))
    if output_text:
        return output_text, "output_text"

    for item in payload.get("output", []):
        text = extract_text_from_content(item.get("content") if isinstance(item, dict) else item)
        if text:
            return text, "output"

    for choice in payload.get("choices", []):
        if not isinstance(choice, dict):
            continue
        text = extract_text_from_content(choice.get("message", {}).get("content"))
        if text:
            return text, "choices.message.content"

    return "", "empty"


def extract_completion_text(completion: Any) -> tuple[str, str]:
    output_text = extract_text_from_content(getattr(completion, "output_text", None))
    if output_text:
        return output_text, "output_text"

    choices = getattr(completion, "choices", None) or []
    for choice in choices:
        message = getattr(choice, "message", None)
        if message is None and isinstance(choice, dict):
            message = choice.get("message")
        if message is None:
            continue
        text = extract_text_from_content(getattr(message, "content", None))
        if not text and isinstance(message, dict):
            text = extract_text_from_content(message.get("content"))
        if text:
            return text, "choices.message.content"

    return extract_text_from_payload(completion)


def get_by_path(payload: Any, path: str) -> Any:
    current = model_to_dict(payload)
    if not path:
        return current

    for segment in path.split("."):
        if isinstance(current, list):
            try:
                index = int(segment)
            except ValueError as exc:
                raise KeyError(f"Expected numeric list index, got: {segment}") from exc
            current = current[index]
            continue
        if not isinstance(current, dict):
            raise KeyError(f"Cannot descend into non-container value at: {segment}")
        if segment not in current:
            raise KeyError(f"Missing key in response payload: {segment}")
        current = current[segment]
    return model_to_dict(current)
