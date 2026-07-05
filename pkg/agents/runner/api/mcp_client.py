import os
from contextlib import AsyncExitStack
from deepeval.tracing import observe
from mcp.client.session import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    get_default_environment,
    stdio_client,
)

# Environment variables the MCP server needs to reach the target cluster and
# cloud APIs. Only these are forwarded (on top of the SDK's safe defaults such as
# PATH/HOME) — the full environment is deliberately NOT passed, to avoid leaking
# unrelated secrets (agent/judge API keys, etc.) into the server subprocess.
MCP_ENV_ALLOWLIST = (
    "KUBECONFIG",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CLOUDSDK_CONFIG",
    "CLOUDSDK_CORE_PROJECT",
    "GOOGLE_CLOUD_PROJECT",
    "USE_GKE_GCLOUD_AUTH_PLUGIN",
)


class MCPClient:

  def __init__(self, server_path: str):
    self.server_path = server_path
    self.exit_stack = AsyncExitStack()
    self.session = None

  async def __aenter__(self):
    # Start from the SDK's safe default environment (PATH, HOME, ...) and add only
    # the allowlisted variables the MCP server needs — chiefly KUBECONFIG and cloud
    # credentials — so it can resolve the target cluster's kubeconfig context.
    # The SDK otherwise launches the server with a stripped environment that lacks
    # KUBECONFIG; forwarding the full os.environ would over-share secrets.
    env = get_default_environment()
    for key in MCP_ENV_ALLOWLIST:
      value = os.environ.get(key)
      if value is not None:
        env[key] = value
    server_params = StdioServerParameters(
        command=self.server_path, env=env
    )
    stdio_transport = await self.exit_stack.enter_async_context(
        stdio_client(server_params)
    )
    self.read_stream, self.write_stream = stdio_transport
    self.session = await self.exit_stack.enter_async_context(
        ClientSession(self.read_stream, self.write_stream)
    )
    await self.session.initialize()
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb):
    await self.exit_stack.aclose()

  async def list_tools(self):
    return await self.session.list_tools()

  @observe(span_type="TOOL")
  async def call_tool(self, name, arguments):
    return await self.session.call_tool(name, arguments=arguments)
