"""Robust ChatOpenRouter implementation for free-tier OpenRouter models.

Free models on OpenRouter often:
1. Wrap their JSON output in markdown code fences (```json ... ```), causing Pydantic's
   model_validate_json to fail with invalid JSON errors.
2. Return content=None when forced with response_format=json_schema.

This class overrides ChatOpenRouter to strip markdown code fences from model outputs
and fallback to text-mode schema injection if content is None or empty.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from typing import Any, TypeVar, overload

from pydantic import BaseModel
from openai.types.shared_params.response_format_json_schema import (
    JSONSchema,
    ResponseFormatJSONSchema,
)

from browser_use.llm.openrouter.chat import ChatOpenRouter
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage, SystemMessage
from browser_use.llm.openrouter.serializer import OpenRouterMessageSerializer
from browser_use.llm.schema import SchemaOptimizer
from browser_use.llm.views import ChatInvokeCompletion

T = TypeVar("T", bound=BaseModel)


def strip_markdown_fences(text: str) -> str:
    """Remove ```json and ``` fences from model output if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def inject_schema_into_messages(
    messages: list[BaseMessage], schema: dict[str, Any]
) -> list[BaseMessage]:
    """Inject JSON schema instructions into system prompt."""
    schema_text = json.dumps(schema, separators=(",", ":"))
    instruction = textwrap.dedent(f"""
        IMPORTANT: You MUST respond with a single valid JSON object that strictly
        conforms to the following JSON schema. Do NOT wrap the JSON in markdown
        code fences. Do NOT add any conversational text before or after the JSON object.

        Schema:
        {schema_text}
    """).strip()

    new_messages: list[BaseMessage] = []
    injected = False
    for msg in messages:
        if not injected and isinstance(msg, SystemMessage):
            new_messages.append(SystemMessage(content=f"{msg.text}\n\n{instruction}"))
            injected = True
        else:
            new_messages.append(msg)

    if not injected:
        new_messages.insert(0, SystemMessage(content=instruction))

    return new_messages


@dataclass
class FreeOpenRouterChat(ChatOpenRouter):
    """Drop-in ChatOpenRouter replacement that handles markdown fences and free model quirks."""

    @overload
    async def ainvoke(
        self, messages: list[BaseMessage], output_format: None = None, **kwargs: Any
    ) -> ChatInvokeCompletion[str]: ...

    @overload
    async def ainvoke(
        self, messages: list[BaseMessage], output_format: type[T], **kwargs: Any
    ) -> ChatInvokeCompletion[T]: ...

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: type[T] | None = None,
        **kwargs: Any,
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        if output_format is None:
            return await super().ainvoke(messages, output_format=None, **kwargs)

        openrouter_messages = OpenRouterMessageSerializer.serialize_messages(messages)
        extra_headers = {}
        if self.http_referer:
            extra_headers["HTTP-Referer"] = self.http_referer

        schema = SchemaOptimizer.create_optimized_json_schema(output_format)
        response_format_schema: JSONSchema = {
            "name": "agent_output",
            "strict": True,
            "schema": schema,
        }

        content: str | None = None
        usage = None

        # Attempt 1: Call API with response_format JSON schema
        try:
            response = await self.get_client().chat.completions.create(
                model=self.model,
                messages=openrouter_messages,
                temperature=self.temperature,
                top_p=self.top_p,
                seed=self.seed,
                response_format=ResponseFormatJSONSchema(
                    json_schema=response_format_schema,
                    type="json_schema",
                ),
                extra_headers=extra_headers,
                **(self.extra_body or {}),
            )
            usage = self._get_usage(response)
            if response.choices and response.choices[0].message:
                content = response.choices[0].message.content
        except Exception:
            content = None

        # Attempt 2: Fallback if response_format yielded no content
        if not content:
            augmented_messages = inject_schema_into_messages(messages, schema)
            openrouter_messages = OpenRouterMessageSerializer.serialize_messages(
                augmented_messages
            )
            response = await self.get_client().chat.completions.create(
                model=self.model,
                messages=openrouter_messages,
                temperature=self.temperature,
                top_p=self.top_p,
                seed=self.seed,
                extra_headers=extra_headers,
                **(self.extra_body or {}),
            )
            usage = self._get_usage(response)
            if response.choices and response.choices[0].message:
                content = response.choices[0].message.content

        if not content:
            raise ModelProviderError(
                message="Model returned empty response content.",
                model=self.name,
            )

        # Strip markdown fences (e.g. ```json ... ```)
        cleaned_content = strip_markdown_fences(content)

        try:
            parsed = output_format.model_validate_json(cleaned_content)
            return ChatInvokeCompletion(completion=parsed, usage=usage)
        except Exception as parse_err:
            raise ModelProviderError(
                message=(
                    f"Failed to parse structured output from model response: {parse_err}. "
                    f"Raw content: {content[:300]!r}"
                ),
                model=self.name,
            ) from parse_err
