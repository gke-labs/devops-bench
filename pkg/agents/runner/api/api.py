import asyncio
import json
import os
import sys
import time

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase
from deepeval.tracing import observe

from mcp_client import MCPClient
from llm_client import LLMClient


@observe(span_type="TOOL")
async def call_mcp_tool(session, name, args):
  """Calls an MCP tool and traces it with DeepEval."""
  return await session.call_tool(name, arguments=args)


async def process_query(
    llm_client, contents, tools, system_instruction, mcp_client
):
  """Process a single turn of the agent."""
  response = await llm_client.generate_content(
      contents, tools, system_instruction
  )

  text_content = llm_client.get_text_content(response)
  function_calls = llm_client.extract_function_calls(response)

  assistant_message = {"role": "assistant", "content": text_content}
  if function_calls:
    assistant_message["tool_calls"] = function_calls
  contents.append(assistant_message)

  if not function_calls:
    return response, contents

  # Handle function calls
  for function_call in function_calls:
    name = function_call["name"]
    args = function_call["args"]
    call_id = function_call.get("id")

    try:
      tool_result = await mcp_client.call_tool(name, args)

      result_text = (
          tool_result.content[0].text
          if hasattr(tool_result, "content")
          and tool_result.content
          and hasattr(tool_result.content[0], "text")
          else str(tool_result)
      )
      
      contents.append({
          "role": "tool",
          "tool_call_id": call_id,
          "name": name,
          "content": result_text
      })
      
    except Exception as e:
      print(f"Error calling tool {name}: {e}")
      contents.append({
          "role": "tool",
          "tool_call_id": call_id,
          "name": name,
          "content": f"Error: {e}"
      })

  return response, contents



async def _run_agent_loop(goal, tools, mcp_client, llm_client):
  """Internal loop for running the agent with given tools."""
  formatted_tools = llm_client.format_tools(tools)

  contents = [
      {"role": "user", "content": goal}
  ]
  turn = 0
  trajectory = []
  tools_used = set()

  while True:
    print(f"\n--- Turn {turn+1} ---")
    response, contents = await process_query(
        llm_client, contents, formatted_tools, None, mcp_client
    )

    function_calls = llm_client.extract_function_calls(response)

    if function_calls:
      for fc in function_calls:
        tools_used.add(fc["name"])
        trajectory.append({
            "name": fc["name"],
            "args": fc["args"],
            "status": "success"
        })

    if not function_calls:
      print("No more function calls. Agent finished.")
      actual_output = llm_client.get_text_content(response)
      usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
      
      # Build detailed trajectory from contents
      trajectory = []
      for msg in contents:
        role = msg["role"]
        if role == "user":
          trajectory.append({
              "type": "user_input",
              "content": msg["content"]
          })
        elif role == "assistant":
          trajectory.append({
              "type": "agent_response",
              "content": msg.get("content", ""),
              "tool_calls": msg.get("tool_calls", [])
          })
        elif role == "tool":
          trajectory.append({
              "type": "tool_output",
              "name": msg.get("name"),
              "content": msg.get("content")
          })
          
      return {
        "output": actual_output, 
        "latency": 0.0,
        "tokens": {
            "prompt_tokens": getattr(usage, "prompt_token_count", 0),
            "candidates_tokens": getattr(usage, "candidates_token_count", 0),
            "total_tokens": getattr(usage, "total_token_count", 0),
        } if usage else None, 
        "tools": list(tools_used),
        "trajectory": trajectory
      }

    turn += 1


@observe(span_type="LLM")
async def run_api_agent(goal, mcp_server_path, llm_client: LLMClient, use_mcp=True):
  """Runs an agent that optionally connects to an MCP server."""
  if use_mcp:
    async with MCPClient(mcp_server_path) as mcp_client:
      result = await mcp_client.list_tools()
      tools = result.tools
      return await _run_agent_loop(goal, tools, mcp_client, llm_client)
  else:
    print("Running without MCP tools.")
    return await _run_agent_loop(goal, [], None, llm_client)
