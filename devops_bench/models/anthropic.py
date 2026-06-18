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

"""Anthropic (Claude on Vertex) adapter for the LLM client interface."""

from __future__ import annotations

from typing import Any

from devops_bench.core.config import get_env, get_int
from devops_bench.core.errors import MissingDependencyError
from devops_bench.core.logging import get_logger
from devops_bench.models.base import MODELS, LLMClient

try:
    from anthropic import AsyncAnthropicVertex
except ImportError:  # pragma: no cover - exercised only without the SDK
    AsyncAnthropicVertex = None

__all__ = ["AnthropicClientAdapter"]

_DEFAULT_MAX_TOKENS = 16000

_log = get_logger("models.anthropic")


@MODELS.register("anthropic")
class AnthropicClientAdapter(LLMClient):
    """Adapter for the Anthropic SDK using ``AsyncAnthropicVertex``.

    Targets Claude models served through Vertex AI; the region and project are
    read from ``GCP_VERTEX_LOCATION`` and ``GCP_PROJECT_ID``.

    Args:
        model_name: Model override; falls back to ``AGENT_MODEL`` when omitted.
        max_tokens: Per-response output token cap; falls back to
            ``AGENT_MAX_TOKENS`` and then a sane default when omitted.

    Raises:
        MissingDependencyError: If the ``anthropic`` SDK is not installed.
    """

    def __init__(self, model_name: str | None = None, max_tokens: int | None = None) -> None:
        if AsyncAnthropicVertex is None:
            raise MissingDependencyError("the Anthropic model adapter", "anthropic")

        project_id = get_env("GCP_PROJECT_ID")
        location = get_env("GCP_VERTEX_LOCATION", "us-central1")

        if not model_name:
            model_name = get_env("AGENT_MODEL", "claude-sonnet-4-5@20250929")

        if not project_id:
            _log.warning(
                "GCP_PROJECT_ID not set; AsyncAnthropicVertex may fail if it "
                "cannot be inferred from the environment.",
            )

        self.client = AsyncAnthropicVertex(region=location, project_id=project_id)
        self.model_name = model_name
        self.max_tokens = max_tokens or get_int("AGENT_MAX_TOKENS", _DEFAULT_MAX_TOKENS)

    async def generate_content(
        self,
        contents: list[dict[str, Any]],
        tools: Any,
        system_instruction: str | None,
    ) -> Any:
        messages = self._convert_to_anthropic_messages(contents)
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if system_instruction:
            kwargs["system"] = system_instruction
        return await self.client.messages.create(**kwargs)

    def format_tools(self, mcp_tools: Any) -> Any:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
            for tool in mcp_tools
        ]

    def extract_function_calls(self, response: Any) -> list[dict]:
        calls: list[dict] = []
        if hasattr(response, "content"):
            for content in response.content:
                if hasattr(content, "type") and content.type == "tool_use":
                    calls.append({"name": content.name, "args": content.input, "id": content.id})
        return calls

    def get_text_content(self, response: Any) -> str:
        text = ""
        if hasattr(response, "content"):
            for content in response.content:
                if hasattr(content, "type") and content.type == "text":
                    text += content.text
        return text

    def _convert_to_anthropic_messages(
        self, contents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        anthropic_messages: list[dict[str, Any]] = []
        for msg in contents:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                if "tool_calls" in msg:
                    content_blocks: list[dict[str, Any]] = []
                    if content:
                        content_blocks.append({"type": "text", "text": content})
                    for tc in msg["tool_calls"]:
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.get("id"),
                                "name": tc.get("name"),
                                "input": tc.get("args"),
                            }
                        )
                    anthropic_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    anthropic_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                # Group consecutive tool results into one user message so that
                # parallel tool calls do not produce back-to-back user turns,
                # which the Anthropic API rejects.
                tool_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id"),
                    "content": content,
                }
                if anthropic_messages and anthropic_messages[-1]["role"] == "user":
                    last = anthropic_messages[-1]["content"]
                    if isinstance(last, list):
                        last.append(tool_block)
                    else:
                        anthropic_messages[-1]["content"] = [
                            {"type": "text", "text": last},
                            tool_block,
                        ]
                else:
                    anthropic_messages.append({"role": "user", "content": [tool_block]})
        return anthropic_messages
