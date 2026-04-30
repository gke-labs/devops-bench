"""LLM Client interface for MCP runner."""

import abc

class LLMClient(abc.ABC):
  """Abstract base class for LLM clients supporting MCP tools."""

  @abc.abstractmethod
  async def generate_content(
      self, contents, tools, system_instruction
  ):
    """Generates content from the model."""
    pass

  @abc.abstractmethod
  def format_tools(self, mcp_tools):
    """Converts MCP tools to the format expected by the model."""
    pass

  @abc.abstractmethod
  def extract_function_calls(self, response):
    """Extracts function calls from the model's response.

    Args:
      response: The raw response from the model.

    Returns:
      A list of dicts, each containing 'name', 'args', and optionally 'id'.
    """
    pass

  @abc.abstractmethod
  def get_text_content(self, response) -> str:
    """Extracts the text content from the model's response.

    Args:
      response: The raw response from the model.
    """
    pass

