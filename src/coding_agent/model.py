"""Provider-neutral LLM adapter for the autonomous coding loop.

The adapter deliberately reuses Odysseus' existing model resolution and
``llm_call_async`` path. It does not introduce a provider SDK or a second
model configuration system.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Sequence


class CodingModelAdapter:
    """Adapt Odysseus' existing model provider abstraction to ``CodingModel``.

    The model is asked for a small JSON envelope so the coding loop can consume
    tool calls consistently across OpenAI-compatible, Ollama and other
    providers already supported by Odysseus.
    """

    def __init__(self, model_spec: str, *, owner: str | None = None, timeout: float = 120.0) -> None:
        self.model_spec = str(model_spec or "").strip()
        self.owner = owner
        self.timeout = float(timeout)
        if not self.model_spec:
            raise ValueError("A coding-agent model is required")

    async def complete(self, messages: Sequence[dict[str, Any]]) -> Mapping[str, Any]:
        from src.ai_interaction import _resolve_model
        from src.llm_core import llm_call_async

        url, model, headers = await asyncio.to_thread(
            _resolve_model, self.model_spec, owner=self.owner
        )
        prompt_messages = list(messages)
        response = await llm_call_async(
            url,
            model,
            prompt_messages,
            headers=headers,
            timeout=self.timeout,
        )
        return parse_coding_response(response)


def parse_coding_response(response: Any) -> dict[str, Any]:
    """Parse a model response into the loop's normalized response envelope.

    Providers sometimes wrap JSON in Markdown fences or return a small amount
    of explanatory text. We accept those harmless wrappers but never execute
    arbitrary text as a tool call.
    """
    text = str(response or "").strip()
    if not text:
        return {"content": "", "tool_calls": [], "done": False}

    payload = _extract_json_object(text)
    if payload is None:
        # A plain response is useful context, but it is never interpreted as a
        # tool request. The loop will issue its continuation/verification prompt.
        return {"content": text, "tool_calls": [], "done": False}

    tool_calls = payload.get("tool_calls", payload.get("tools", []))
    if not isinstance(tool_calls, list):
        tool_calls = []

    normalized: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, Mapping):
            continue
        name = str(call.get("name") or call.get("tool") or "").strip()
        if not name:
            continue
        arguments = call.get("arguments", call.get("args", {}))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                # Preserve malformed arguments as data so the loop can ask the
                # model to correct them instead of executing a guessed command.
                arguments = {"raw": arguments}
        if not isinstance(arguments, Mapping):
            arguments = {"value": arguments}
        normalized.append({"name": name, "arguments": dict(arguments)})

    return {
        "content": str(payload.get("content") or "").strip(),
        "tool_calls": normalized,
        "done": bool(payload.get("done", False)),
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidates = [text]
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            candidates.append("\n".join(lines[1:-1]).strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
