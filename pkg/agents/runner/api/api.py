import asyncio
import glob
import re
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

def parse_skill_md(file_path):
  try:
    with open(file_path, "r") as f:
      content = f.read()
      match = re.search(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL | re.MULTILINE)
      if match:
        frontmatter = match.group(1)
        name_match = re.search(r"^name:\s*(.*?)\s*$", frontmatter, re.MULTILINE)
        desc_match = re.search(r"^description:\s*(.*?)\s*$", frontmatter, re.MULTILINE)
        
        name = name_match.group(1).strip().strip('"').strip("'") if name_match else None
        description = desc_match.group(1).strip().strip('"').strip("'") if desc_match else None
        return name, description, content
  except Exception as e:
    print(f"Error parsing skill file {file_path}: {e}")
  return None, None, None


async def process_query(
    llm_client, contents, tools, system_instruction, mcp_client
):
  """Process a single turn of the agent."""
  start_time = time.time()
  response = await llm_client.generate_content(
      contents, tools, system_instruction
  )
  duration = time.time() - start_time

  text_content = llm_client.get_text_content(response)
  function_calls = llm_client.extract_function_calls(response)

  assistant_message = {"role": "assistant", "content": text_content}
  if function_calls:
    assistant_message["tool_calls"] = function_calls
  contents.append(assistant_message)

  if not function_calls:
    return response, contents, duration

  # Handle function calls
  for function_call in function_calls:
    name = function_call["name"]
    args = function_call["args"]
    call_id = function_call.get("id")

    try:
      # Check if it is a skill tool
      if hasattr(mcp_client, "skill_resources") and name in mcp_client.skill_resources:
        file_path = mcp_client.skill_resources[name]
        print(f"Calling skill tool {name} for file {file_path}")
        try:
          with open(file_path, "r") as f:
            result_text = f.read()
        except Exception as e:
          result_text = f"Error reading skill file {file_path}: {e}"
      else:
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

  return response, contents, duration



async def _run_agent_loop(goal, tools, mcp_client, llm_client, system_instruction=None):
  """Internal loop for running the agent with given tools."""
  total_latency = 0.0
  formatted_tools = llm_client.format_tools(tools)

  contents = [
      {"role": "user", "content": goal}
  ]
  turn = 0
  trajectory = []
  tools_used = set()

  while True:
    print(f"\n--- Turn {turn+1} ---")
    response, contents, duration = await process_query(
        llm_client, contents, formatted_tools, system_instruction, mcp_client
    )
    total_latency += duration

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
        "latency": total_latency,
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
async def run_api_agent(goal, mcp_server_path, llm_client: LLMClient, bench_use_mcp=True, system_instruction=None):
  """Runs an agent that optionally connects to an MCP server."""
  class ToolInfo:
    def __init__(self, name, description, inputSchema=None):
      self.name = name
      self.description = description
      self.inputSchema = inputSchema

  if bench_use_mcp:
    async with MCPClient(mcp_server_path) as mcp_client:
      tools_result = await mcp_client.list_tools()
      tools = list(tools_result.tools)

      # Load skills from local files in gke-mcp repo
      mcp_client.skill_resources = {}
      skills_dir = "third_party/gke-mcp/skills"
      if os.path.exists(skills_dir):
        skill_files = glob.glob(os.path.join(skills_dir, "**/SKILL.md"), recursive=True)
        for file_path in skill_files:
          skill_name, description, _ = parse_skill_md(file_path)
          if skill_name:
            normalized_name = "skill_" + skill_name.replace("-", "_")
            skill_tool = ToolInfo(
                name=normalized_name,
                description=description or f"Exposes skill: {skill_name}",
            )
            tools.append(skill_tool)
            mcp_client.skill_resources[normalized_name] = file_path
            print(f"Loaded local skill as tool: {normalized_name} -> {file_path}")
      else:
        print(f"Skills directory not found: {skills_dir}")
      return await _run_agent_loop(goal, tools, mcp_client, llm_client, system_instruction=system_instruction)
  else:
    print("Running without MCP tools.")
    return await _run_agent_loop(goal, [], None, llm_client, system_instruction=system_instruction)
