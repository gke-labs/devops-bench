import os
from contextlib import AsyncExitStack
from deepeval.tracing import observe
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

class MCPClient:

  def __init__(self, server_path: str):
    self.server_path = server_path
    self.exit_stack = AsyncExitStack()
    self.session = None

  async def __aenter__(self):
    # Forward the full environment so the MCP server inherits KUBECONFIG and
    # cloud credentials (GOOGLE_APPLICATION_CREDENTIALS, etc.). The MCP SDK
    # otherwise launches the server with a stripped default environment, which
    # leaves it unable to resolve the target cluster's kubeconfig context.
    server_params = StdioServerParameters(
        command=self.server_path, env=os.environ.copy()
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
