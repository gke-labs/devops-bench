import time
from deepeval.tracing import observe
from google import genai


@observe()
def run_api_agent(model, prompt):
    """Calls Gemini API directly."""
    client = genai.Client()
    start_time = time.time()
    response = client.models.generate_content(model=model, contents=prompt)
    latency = time.time() - start_time
    
    tokens = {}
    if hasattr(response, "usage_metadata"):
        tokens = {
            "input": response.usage_metadata.prompt_token_count,
            "candidates": response.usage_metadata.candidates_token_count,
            "total": response.usage_metadata.total_token_count,
            "cached": getattr(response.usage_metadata, "cached_content_token_count", 0)
        }
        
    return {
        "output": response.text,
        "latency": latency,
        "tokens": tokens,
        "tools": {}
    }
