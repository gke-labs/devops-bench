import os
from google import genai
from google.genai import types
from llm_client import LLMClient
from utils import filter_schema_for_gemini
from anthropic import AsyncAnthropicVertex

class GeminiClientAdapter(LLMClient):
  """Adapter for Gemini SDK."""

  def __init__(self, model_name="gemini-2.5-flash"):
    project_id = os.environ.get("VERTEX_PROJECT_ID")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    
    if project_id:
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
    if response.function_calls:
      for fc in response.function_calls:
        calls.append({
            "name": fc.name,
            "args": fc.args,
            "id": None
        })
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
    project_id = os.environ.get("VERTEX_PROJECT_ID")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    
    if not model_name:
      model_name = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5@20250929")
        
    if not project_id:
      print("Warning: VERTEX_PROJECT_ID not set. AsyncAnthropicVertex may fail if not inferred from environment.")
        
    self.client = AsyncAnthropicVertex(region=location, project_id=project_id)
    self.model_name = model_name

  async def generate_content(self, contents, tools, system_instruction):
    messages = self._convert_to_anthropic_messages(contents)
    return await self.client.messages.create(
        model=self.model_name,
        max_tokens=4096,
        messages=messages,
        tools=tools,
        system=system_instruction,
    )

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
