"""Tests for OllamaClientAdapter and OllamaDeepEvalModel."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# llm_adapters uses bare imports (from llm_client import ..., from utils import ...)
# that resolve relative to the api package directory.
_api_dir = str(Path(__file__).resolve().parents[1] / "pkg/agents/runner/api")
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

from llm_adapters import OllamaClientAdapter
from pkg.evaluator.evaluate import OllamaDeepEvalModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adapter(model="gemma4:e2b"):
    """Create an OllamaClientAdapter with a mock async client."""
    with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://fake:11434/v1",
                                  "AGENT_MODEL": model}):
        a = OllamaClientAdapter(model_name=model)
    a.client = MagicMock()
    return a


def _deep_eval_model(model="gemma4:e2b"):
    """Create an OllamaDeepEvalModel with a mock sync client."""
    with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://fake:11434/v1",
                                  "JUDGE_MODEL": model}):
        m = OllamaDeepEvalModel(model_name=model)
    m.client = MagicMock()
    return m


def _make_tool(name="apply_manifest", description="Apply a k8s manifest", schema=None):
    t = MagicMock()
    t.name = name
    t.description = description
    t.inputSchema = schema or {"type": "object", "properties": {"manifest": {"type": "string"}}}
    return t


def _make_response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _make_tool_call(name, arguments, call_id="call_abc"):
    func = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=call_id, function=func)


def _completion(content):
    """Minimal OpenAI ChatCompletion response for OllamaDeepEvalModel."""
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


# ---------------------------------------------------------------------------
# OllamaClientAdapter — format_tools
# ---------------------------------------------------------------------------

class TestFormatTools:
    def test_single_tool(self):
        result = _adapter().format_tools([_make_tool()])
        assert len(result) == 1
        entry = result[0]
        assert entry["type"] == "function"
        assert entry["function"]["name"] == "apply_manifest"
        assert entry["function"]["description"] == "Apply a k8s manifest"

    def test_parameters_passed_through(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        result = _adapter().format_tools([_make_tool(schema=schema)])
        assert result[0]["function"]["parameters"] == schema

    def test_multiple_tools(self):
        tools = [_make_tool("t1"), _make_tool("t2")]
        result = _adapter().format_tools(tools)
        assert [e["function"]["name"] for e in result] == ["t1", "t2"]

    def test_tool_without_input_schema_attribute(self):
        tool = MagicMock(spec=[])        # no inputSchema attribute
        tool.name = "no_schema"
        tool.description = "desc"
        result = _adapter().format_tools([tool])
        assert result[0]["function"]["parameters"] == {}

    def test_empty_tool_list(self):
        assert _adapter().format_tools([]) == []


# ---------------------------------------------------------------------------
# OllamaClientAdapter — extract_function_calls
# ---------------------------------------------------------------------------

class TestExtractFunctionCalls:
    def test_no_tool_calls(self):
        assert _adapter().extract_function_calls(_make_response(content="hi")) == []

    def test_dict_args(self):
        args = {"manifest": "apiVersion: v1"}
        tc = _make_tool_call("apply", args, call_id="c1")
        calls = _adapter().extract_function_calls(_make_response(tool_calls=[tc]))
        assert calls == [{"name": "apply", "args": args, "id": "c1"}]

    def test_json_string_args_are_parsed(self):
        args = {"namespace": "default"}
        tc = _make_tool_call("get", json.dumps(args), call_id="c2")
        calls = _adapter().extract_function_calls(_make_response(tool_calls=[tc]))
        assert calls[0]["args"] == args

    def test_malformed_json_string_falls_back_to_empty_dict(self):
        tc = _make_tool_call("bad", "{not: json}", call_id="c3")
        calls = _adapter().extract_function_calls(_make_response(tool_calls=[tc]))
        assert calls[0]["args"] == {}

    def test_multiple_tool_calls(self):
        tcs = [
            _make_tool_call("a", {"x": 1}, "id_a"),
            _make_tool_call("b", '{"y": 2}', "id_b"),
        ]
        calls = _adapter().extract_function_calls(_make_response(tool_calls=tcs))
        assert len(calls) == 2
        assert calls[0]["name"] == "a"
        assert calls[1]["args"] == {"y": 2}


# ---------------------------------------------------------------------------
# OllamaClientAdapter — get_text_content
# ---------------------------------------------------------------------------

class TestGetTextContent:
    def test_returns_content(self):
        assert _adapter().get_text_content(_make_response(content="ok")) == "ok"

    def test_none_content_returns_empty_string(self):
        assert _adapter().get_text_content(_make_response(content=None)) == ""

    def test_empty_string_content(self):
        assert _adapter().get_text_content(_make_response(content="")) == ""


# ---------------------------------------------------------------------------
# OllamaClientAdapter — _convert_to_openai_messages
# ---------------------------------------------------------------------------

class TestConvertToOpenAIMessages:
    def test_system_instruction_prepended(self):
        msgs = _adapter()._convert_to_openai_messages(
            [{"role": "user", "content": "hello"}],
            system_instruction="Be helpful.",
        )
        assert msgs[0] == {"role": "system", "content": "Be helpful."}
        assert msgs[1]["role"] == "user"

    def test_no_system_instruction(self):
        msgs = _adapter()._convert_to_openai_messages(
            [{"role": "user", "content": "hi"}], system_instruction=None
        )
        assert not any(m["role"] == "system" for m in msgs)

    def test_user_message(self):
        msgs = _adapter()._convert_to_openai_messages(
            [{"role": "user", "content": "deploy"}], system_instruction=None
        )
        assert msgs == [{"role": "user", "content": "deploy"}]

    def test_assistant_message_no_tool_calls(self):
        msgs = _adapter()._convert_to_openai_messages(
            [{"role": "assistant", "content": "done"}], system_instruction=None
        )
        assert msgs == [{"role": "assistant", "content": "done"}]

    def test_assistant_message_with_tool_calls(self):
        contents = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"name": "apply", "args": {"x": 1}, "id": "call_x"}],
        }]
        msgs = _adapter()._convert_to_openai_messages(contents, system_instruction=None)
        tc = msgs[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["id"] == "call_x"
        assert tc["function"]["name"] == "apply"
        # args must be serialised to a JSON string in the OpenAI wire format
        assert tc["function"]["arguments"] == json.dumps({"x": 1})

    def test_tool_call_string_args_passed_through_unchanged(self):
        contents = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"name": "t", "args": '{"k": "v"}', "id": "c"}],
        }]
        msgs = _adapter()._convert_to_openai_messages(contents, system_instruction=None)
        assert msgs[0]["tool_calls"][0]["function"]["arguments"] == '{"k": "v"}'

    def test_tool_result_message(self):
        contents = [{"role": "tool", "tool_call_id": "c1", "content": "applied"}]
        msgs = _adapter()._convert_to_openai_messages(contents, system_instruction=None)
        assert msgs == [{"role": "tool", "tool_call_id": "c1", "content": "applied"}]

    def test_full_conversation_role_order(self):
        contents = [
            {"role": "user", "content": "do X"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"name": "t", "args": {}, "id": "c1"}
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            {"role": "assistant", "content": "done"},
        ]
        msgs = _adapter()._convert_to_openai_messages(contents, system_instruction="sys")
        assert [m["role"] for m in msgs] == [
            "system", "user", "assistant", "tool", "assistant"
        ]


# ---------------------------------------------------------------------------
# OllamaDeepEvalModel
# ---------------------------------------------------------------------------

class TestOllamaDeepEvalModel:
    def test_generate_returns_text(self):
        m = _deep_eval_model()
        m.client.chat.completions.create.return_value = _completion("The score is 9.")
        assert m.generate("Evaluate this.") == "The score is 9."

    def test_generate_none_content_returns_empty_string(self):
        m = _deep_eval_model()
        m.client.chat.completions.create.return_value = _completion(None)
        assert m.generate("prompt") == ""

    def test_generate_sends_correct_model_and_messages(self):
        m = _deep_eval_model(model="gemma4:e2b")
        m.client.chat.completions.create.return_value = _completion("ok")
        m.generate("my prompt")
        kwargs = m.client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gemma4:e2b"
        assert kwargs["messages"] == [{"role": "user", "content": "my prompt"}]

    @pytest.mark.asyncio
    async def test_a_generate_delegates_to_generate(self):
        m = _deep_eval_model()
        m.client.chat.completions.create.return_value = _completion("async result")
        assert await m.a_generate("prompt") == "async result"

    def test_get_model_name(self):
        assert _deep_eval_model(model="gemma4:e2b").get_model_name() == "gemma4:e2b"
