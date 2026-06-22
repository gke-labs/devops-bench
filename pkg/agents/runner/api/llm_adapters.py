import os
import json
import base64
from google import genai
from google.genai import types
from llm_client import LLMClient
from utils import filter_schema_for_gemini
from anthropic import AsyncAnthropicVertex

class GeminiClientAdapter(LLMClient):
  """Adapter for Gemini SDK."""

  def __init__(self, model_name=None):
    if not model_name:
      model_name = os.environ.get("AGENT_MODEL", "gemini-3.1-pro-preview")

    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_VERTEX_LOCATION", "us-central1")
    api_key = os.environ.get("AGENT_API_KEY")

    if api_key:
      self.client = genai.Client(api_key=api_key)
    elif project_id:
      self.client = genai.Client(vertexai=True, project=project_id, location=location)
    else:
      self.client = genai.Client()

    self.model_name = model_name

  async def generate_content(self, contents, tools, system_instruction):
    gemini_contents = self._convert_to_gemini_messages(contents)

    config_args = {"system_instruction": system_instruction}
    if tools and hasattr(tools, "function_declarations") and tools.function_declarations:
      config_args["tools"] = [tools]

    return await self.client.aio.models.generate_content(
        model=self.model_name,
        contents=gemini_contents,
        config=types.GenerateContentConfig(**config_args),
    )

  def format_tools(self, mcp_tools):
    return types.Tool(
        function_declarations=[
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": (
                    filter_schema_for_gemini(tool.inputSchema)
                    if hasattr(tool, "inputSchema")
                    and isinstance(tool.inputSchema, dict)
                    else None
                ),
            }
            for tool in mcp_tools
        ]
    )

  def extract_function_calls(self, response):
    calls = []
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
      for part in response.candidates[0].content.parts:
        if part.function_call:
          fc = part.function_call
          call_info = {
              "name": fc.name,
              "args": fc.args,
              "id": None
          }
          if part.thought_signature:
            call_info["thought_signature"] = base64.b64encode(part.thought_signature).decode('utf-8')
          calls.append(call_info)
    return calls

  def get_text_content(self, response) -> str:
    return response.text if response.text else ""

  def _convert_to_gemini_messages(self, contents):
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
              parts.append(types.Part(
                  function_call=types.FunctionCall(name=tc["name"], args=tc["args"]),
                  thought_signature=base64.b64decode(tc["thought_signature"])
              ))
            else:
              parts.append(types.Part.from_function_call(name=tc["name"], args=tc["args"]))
        gemini_contents.append(types.Content(role="model", parts=parts))
      elif role == "tool":
        gemini_contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=msg["name"], response={"result": content}
                    )
                ],
            )
        )
    return gemini_contents


class AnthropicClientAdapter(LLMClient):
  """Adapter for Anthropic SDK."""

  def __init__(self, model_name=None):
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_VERTEX_LOCATION", "us-central1")

    if not model_name:
      model_name = os.environ.get("AGENT_MODEL", "claude-sonnet-4-5@20250929")

    if not project_id:
      print("Warning: GCP_PROJECT_ID not set. AsyncAnthropicVertex may fail if not inferred from environment.")

    self.client = AsyncAnthropicVertex(region=location, project_id=project_id)
    self.model_name = model_name

  async def generate_content(self, contents, tools, system_instruction):
    messages = self._convert_to_anthropic_messages(contents)
    kwargs = {
        "model": self.model_name,
        "max_tokens": 4096,
        "messages": messages,
        "tools": tools,
    }
    if system_instruction:
      kwargs["system"] = system_instruction
    print(f"DEBUG: Anthropic Messages: {messages}")
    return await self.client.messages.create(**kwargs)

  def format_tools(self, mcp_tools):
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
        }
        for tool in mcp_tools
    ]

  def extract_function_calls(self, response):
    calls = []
    if hasattr(response, "content"):
      for content in response.content:
        if hasattr(content, "type") and content.type == "tool_use":
          calls.append({
              "name": content.name,
              "args": content.input,
              "id": content.id
          })
    return calls

  def get_text_content(self, response) -> str:
    text = ""
    if hasattr(response, "content"):
      for content in response.content:
        if hasattr(content, "type") and content.type == "text":
          text += content.text
    return text

  def _convert_to_anthropic_messages(self, contents):
    anthropic_messages = []
    for msg in contents:
      role = msg["role"]
      content = msg["content"]

      if role == "user":
        anthropic_messages.append({"role": "user", "content": content})
      elif role == "assistant":
        if "tool_calls" in msg:
          content_blocks = []
          if content:
            content_blocks.append({"type": "text", "text": content})
          for tc in msg["tool_calls"]:
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": tc.get("name"),
                "input": tc.get("args"),
            })
          anthropic_messages.append(
              {"role": "assistant", "content": content_blocks}
          )
        else:
          anthropic_messages.append({"role": "assistant", "content": content})
      elif role == "tool":
        anthropic_messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id"),
                    "content": content,
                }
            ],
        })
    return anthropic_messages


class OllamaClientAdapter(LLMClient):
  """Adapter for Ollama via its OpenAI-compatible API."""

  def __init__(self, model_name=None):
    from openai import AsyncOpenAI
    if not model_name:
      model_name = os.environ.get("AGENT_MODEL", "gemma4:2b")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    # api_key is required by the openai client but unused by Ollama
    self.client = AsyncOpenAI(base_url=base_url, api_key="ollama")
    self.model_name = model_name

  async def generate_content(self, contents, tools, system_instruction):
    messages = self._convert_to_openai_messages(contents, system_instruction)
    kwargs = {"model": self.model_name, "messages": messages}
    if tools:
      kwargs["tools"] = tools
    return await self.client.chat.completions.create(**kwargs)

  def format_tools(self, mcp_tools):
    return [
      {
        "type": "function",
        "function": {
          "name": tool.name,
          "description": tool.description,
          "parameters": tool.inputSchema if hasattr(tool, "inputSchema") else {},
        },
      }
      for tool in mcp_tools
    ]

  def extract_function_calls(self, response):
    calls = []
    message = response.choices[0].message
    if message.tool_calls:
      for tc in message.tool_calls:
        args = tc.function.arguments
        if isinstance(args, str):
          try:
            args = json.loads(args)
          except json.JSONDecodeError:
            args = {}
        calls.append({"name": tc.function.name, "args": args, "id": tc.id})
    return calls

  def get_text_content(self, response) -> str:
    content = response.choices[0].message.content
    return content if content else ""

  def _convert_to_openai_messages(self, contents, system_instruction):
    messages = []
    if system_instruction:
      messages.append({"role": "system", "content": system_instruction})
    for msg in contents:
      role = msg["role"]
      content = msg["content"]
      if role == "user":
        messages.append({"role": "user", "content": content})
      elif role == "assistant":
        if "tool_calls" in msg:
          tool_calls = [
            {
              "id": tc.get("id") or f"call_{i}",
              "type": "function",
              "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["args"]) if isinstance(tc["args"], dict) else tc["args"],
              },
            }
            for i, tc in enumerate(msg["tool_calls"])
          ]
          messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
        else:
          messages.append({"role": "assistant", "content": content})
      elif role == "tool":
        messages.append({
          "role": "tool",
          "tool_call_id": msg.get("tool_call_id", ""),
          "content": content,
        })
    return messages
