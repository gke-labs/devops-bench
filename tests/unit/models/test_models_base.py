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

"""Tests for the LLM client interface and the provider factory."""

from __future__ import annotations

import os

import pytest

from devops_bench.core.errors import NotRegisteredError
from devops_bench.models.base import MODELS, LLMClient, get_model


def test_registry_has_known_providers():
    # Importing the adapter modules registers them under their canonical keys.
    from devops_bench.models import claude, gemini, ollama  # noqa: F401

    assert MODELS.get("gemini") is gemini.GeminiClientAdapter
    assert MODELS.get("claude") is claude.ClaudeClientAdapter
    assert MODELS.get("ollama") is ollama.OllamaClientAdapter


def test_get_model_returns_gemini_adapter(mocker):
    from devops_bench.models import gemini

    mocker.patch.object(gemini.genai, "Client")
    client = get_model(provider="gemini")

    assert isinstance(client, gemini.GeminiClientAdapter)
    assert isinstance(client, LLMClient)


def test_get_model_resolves_google_alias(mocker):
    from devops_bench.models import gemini

    mocker.patch.object(gemini.genai, "Client")
    client = get_model(provider="google")

    assert isinstance(client, gemini.GeminiClientAdapter)


@pytest.mark.parametrize("provider", ["google-vertex", "google_vertex"])
def test_get_model_resolves_google_vertex_alias(mocker, provider):
    from devops_bench.models import gemini

    mocker.patch.object(gemini.genai, "Client")
    client = get_model(provider=provider)

    assert isinstance(client, gemini.GeminiClientAdapter)


def test_get_model_returns_claude_adapter(mocker):
    from devops_bench.models import claude

    mocker.patch.object(claude, "AsyncAnthropicVertex")
    client = get_model(provider="claude")

    assert isinstance(client, claude.ClaudeClientAdapter)


def test_get_model_resolves_anthropic_alias(mocker):
    from devops_bench.models import claude

    mocker.patch.object(claude, "AsyncAnthropicVertex")
    client = get_model(provider="anthropic")

    assert isinstance(client, claude.ClaudeClientAdapter)


def test_get_model_returns_ollama_adapter(mocker):
    from devops_bench.models import ollama

    mocker.patch.object(ollama, "AsyncOpenAI")
    client = get_model(provider="ollama")

    assert isinstance(client, ollama.OllamaClientAdapter)


def test_get_model_is_case_insensitive(mocker):
    from devops_bench.models import claude

    mocker.patch.object(claude, "AsyncAnthropicVertex")
    client = get_model(provider="CLAUDE")

    assert isinstance(client, claude.ClaudeClientAdapter)


def test_get_model_defaults_to_gemini(mocker):
    from devops_bench.models import gemini

    mocker.patch.object(gemini.genai, "Client")
    mocker.patch.dict(os.environ, {}, clear=True)
    client = get_model()

    assert isinstance(client, gemini.GeminiClientAdapter)


def test_get_model_reads_provider_from_env(mocker):
    from devops_bench.models import claude

    mocker.patch.object(claude, "AsyncAnthropicVertex")
    mocker.patch.dict(os.environ, {"AGENT_PROVIDER": "claude"}, clear=True)
    client = get_model()

    assert isinstance(client, claude.ClaudeClientAdapter)


def test_get_model_passes_model_name(mocker):
    from devops_bench.models import gemini

    mocker.patch.object(gemini.genai, "Client")
    client = get_model(provider="gemini", model_name="gemini-custom")

    assert client.model_name == "gemini-custom"


def test_get_model_unknown_provider_raises(mocker):
    from devops_bench.models import claude, gemini  # noqa: F401

    with pytest.raises(NotRegisteredError):
        get_model(provider="does-not-exist")
