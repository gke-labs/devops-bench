# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Gemini (google-genai) adapter for the LLM client interface."""

from __future__ import annotations

import base64
from typing import Any

from devops_bench.core.config import get_env
from devops_bench.core.errors import MissingDependencyError
from devops_bench.models.base import MODELS, LLMClient

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised only without the SDK
    genai = None
    types = None

__all__ = ["GeminiClientAdapter", "filter_schema_for_gemini"]

_SUPPORTED_SCHEMA_FIELDS = frozenset(
    {
        "type",
        "format",
        "description",
        "nullable",
        "enum",
        "items",
        "properties",
        "required",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "anyOf",
        "oneOf",
        "$defs",
        "$ref",
    }
)

_SCHEMA_FIELD_NAMES = ("items",)
_LIST_SCHEMA_FIELD_NAMES = ("anyOf", "any_of", "oneOf", "one_of")
_DICT_SCHEMA_FIELD_NAMES = ("properties", "defs", "$defs")


def filter_schema_for_gemini(schema: Any) -> Any:
    """Filter a JSON schema down to the subset supported by the Gemini API.

    Recursively drops unsupported fields, upper-cases ``type`` values, and maps
    nullable union types (``["string", "null"]``) to ``nullable: True``.

    Args:
        schema: A JSON schema fragment (dict, bool, or scalar).

    Returns:
        The filtered schema. Returns ``{}`` for ``True``, ``None`` for
        ``False``, and non-dict inputs unchanged.
    """
    if isinstance(schema, bool):
        return {} if schema else None
    if not isinstance(schema, dict):
        return schema

    filtered_schema: dict[str, Any] = {}
    for field_name, field_value in schema.items():
        if field_name == "type":
            if isinstance(field_value, list):
                if "null" in field_value:
                    filtered_schema["nullable"] = True
                    non_null_types = [t for t in field_value if t != "null"]
                    if non_null_types:
                        filtered_schema["type"] = non_null_types[0].upper()
                    else:
                        filtered_schema["type"] = "NULL"
                elif field_value:
                    filtered_schema["type"] = field_value[0].upper()
            elif isinstance(field_value, str):
                filtered_schema["type"] = field_value.upper()
        elif field_name in _SCHEMA_FIELD_NAMES:
            filtered_value = filter_schema_for_gemini(field_value)
            if filtered_value is not None:
                filtered_schema[field_name] = filtered_value
        elif field_name in _LIST_SCHEMA_FIELD_NAMES:
            if isinstance(field_value, list):
                filtered_schema[field_name] = [
                    v
                    for v in (filter_schema_for_gemini(value) for value in field_value)
                    if v is not None
                ]
            else:
                filtered_schema[field_name] = field_value
        elif field_name in _DICT_SCHEMA_FIELD_NAMES:
            if isinstance(field_value, dict):
                filtered_dict: dict[str, Any] = {}
                for key, value in field_value.items():
                    filtered_value = filter_schema_for_gemini(value)
                    if filtered_value is not None:
                        filtered_dict[key] = filtered_value
                filtered_schema[field_name] = filtered_dict
            else:
                filtered_schema[field_name] = field_value
        elif field_name in _SUPPORTED_SCHEMA_FIELDS:
            filtered_schema[field_name] = field_value

    return filtered_schema


@MODELS.register("gemini")
class GeminiClientAdapter(LLMClient):
    """Adapter for the Gemini SDK (google-genai).

    Selects the client backend from the environment: an explicit
    ``AGENT_API_KEY`` takes precedence, then Vertex via ``GCP_PROJECT_ID``,
    otherwise the SDK's default credential resolution.

    Args:
        model_name: Model override; falls back to ``AGENT_MODEL`` when omitted.

    Raises:
        MissingDependencyError: If the ``google-genai`` SDK is not installed.
    """

    def __init__(self, model_name: str | None = None) -> None:
        if genai is None:
            raise MissingDependencyError("the Gemini model adapter", "gemini")

        if not model_name:
            model_name = get_env("AGENT_MODEL", "gemini-3.1-pro-preview")

        project_id = get_env("GCP_PROJECT_ID")
        location = get_env("GCP_VERTEX_LOCATION", "us-central1")
        api_key = get_env("AGENT_API_KEY")

        if api_key:
            self.client = genai.Client(api_key=api_key)
        elif project_id:
            self.client = genai.Client(vertexai=True, project=project_id, location=location)
        else:
            self.client = genai.Client()

        self.model_name = model_name

    async def generate_content(
        self,
        contents: list[dict[str, Any]],
        tools: Any,
        system_instruction: str | None,
    ) -> Any:
        gemini_contents = self._convert_to_gemini_messages(contents)

        config_args: dict[str, Any] = {}
        if system_instruction is not None:
            config_args["system_instruction"] = system_instruction
        if tools and hasattr(tools, "function_declarations") and tools.function_declarations:
            config_args["tools"] = [tools]

        return await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=gemini_contents,
            config=types.GenerateContentConfig(**config_args),
        )

    def format_tools(self, mcp_tools: Any) -> Any:
        return types.Tool(
            function_declarations=[
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": (
                        filter_schema_for_gemini(tool.inputSchema)
                        if hasattr(tool, "inputSchema") and isinstance(tool.inputSchema, dict)
                        else None
                    ),
                }
                for tool in mcp_tools
            ]
        )

    def extract_function_calls(self, response: Any) -> list[dict]:
        calls: list[dict] = []
        candidates = response.candidates
        if candidates and candidates[0].content and candidates[0].content.parts:
            for part in candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    call_info: dict[str, Any] = {"name": fc.name, "args": fc.args, "id": None}
                    sig = getattr(part, "thought_signature", None)
                    if sig:
                        call_info["thought_signature"] = base64.b64encode(sig).decode("utf-8")
                    calls.append(call_info)
        return calls

    def get_text_content(self, response: Any) -> str:
        try:
            return response.text or ""
        except (ValueError, AttributeError):
            parts = []
            cands = getattr(response, "candidates", None)
            if cands and cands[0].content and cands[0].content.parts:
                parts = [p.text for p in cands[0].content.parts if getattr(p, "text", None)]
            return "".join(parts)

    def _convert_to_gemini_messages(self, contents: list[dict[str, Any]]) -> list[Any]:
        gemini_contents = []
        for msg in contents:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                gemini_contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=content)])
                )
            elif role == "assistant":
                parts = []
                if content:
                    parts.append(types.Part.from_text(text=content))
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        if "thought_signature" in tc:
                            parts.append(
                                types.Part(
                                    function_call=types.FunctionCall(
                                        name=tc["name"], args=tc["args"]
                                    ),
                                    thought_signature=base64.b64decode(tc["thought_signature"]),
                                )
                            )
                        else:
                            parts.append(
                                types.Part.from_function_call(name=tc["name"], args=tc["args"])
                            )
                gemini_contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                # Group consecutive tool results into the previous user Content
                # so parallel tool results do not produce back-to-back user
                # turns, which the Gemini API rejects.
                part = types.Part.from_function_response(
                    name=msg["name"], response={"result": content}
                )
                if gemini_contents and gemini_contents[-1].role == "user":
                    gemini_contents[-1].parts.append(part)
                else:
                    gemini_contents.append(types.Content(role="user", parts=[part]))
        return gemini_contents
