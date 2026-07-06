#!/usr/bin/env python3
"""
Minimal mock of Ollama's OpenAI-compatible chat API for integration testing.

Detects whether a request is an agent call or a DeepEval GEval call by
inspecting the prompt, then returns an appropriate canned response.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MOCK_MODEL = "gemma4:2b"

AGENT_RESPONSE = (
    "I'll configure the HTTP-to-HTTPS redirect on public-gw.\n\n"
    "Here is the HTTPRoute manifest:\n\n"
    "```yaml\napiVersion: gateway.networking.k8s.io/v1\n"
    "kind: HTTPRoute\nmetadata:\n  name: https-redirect\n  namespace: default\n"
    "spec:\n  parentRefs:\n  - group: gateway.networking.k8s.io\n    kind: Gateway\n"
    "    name: public-gw\n    port: 80\n  rules:\n  - filters:\n"
    "    - type: RequestRedirect\n      requestRedirect:\n        scheme: https\n"
    "        statusCode: 301\n```"
)

# DeepEval GEval asks the judge to produce evaluation *steps* (list) then a *score*.
# Both must be valid JSON matching the schemas DeepEval expects.
STEPS_JSON = json.dumps(
    {
        "steps": [
            "Check that the output produces a valid Gateway API HTTPRoute manifest.",
            "Verify the HTTPRoute listens on port 80 and targets public-gw.",
            "Confirm a RequestRedirect filter sets scheme=https and statusCode=301.",
        ]
    }
)

SCORE_JSON = json.dumps(
    {
        "reason": (
            "The output is a complete HTTPRoute manifest with a RequestRedirect "
            "filter targeting port 80 and returning 301 to https."
        ),
        "score": 1,
    }
)

_lock = threading.Lock()
_call_count = 0


def _all_text(body: dict) -> str:
    return " ".join(m.get("content", "") for m in body.get("messages", []))


def _classify(body: dict) -> str:
    """Return 'steps', 'score', or 'agent'."""
    text = _all_text(body).lower()
    # DeepEval GEval step-generation: asks to generate evaluation steps
    if "generate" in text and "evaluation steps" in text:
        return "steps"
    # DeepEval GEval scoring: asks for both score and reason as JSON
    if '"score"' in text and '"reason"' in text:
        return "score"
    return "agent"


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[mock] {fmt % args}")

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/v1/models", "/api/tags"):
            self._json(
                {
                    "object": "list",
                    "data": [{"id": MOCK_MODEL, "object": "model"}],
                    "models": [{"name": MOCK_MODEL}],
                }
            )
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        global _call_count
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        with _lock:
            _call_count += 1
            n = _call_count

        kind = _classify(body)
        if kind == "steps":
            text = STEPS_JSON
        elif kind == "score":
            text = SCORE_JSON
        else:
            text = AGENT_RESPONSE

        print(f"[mock] call #{n} ({kind})")
        self._json(
            {
                "id": f"chatcmpl-{n}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", MOCK_MODEL),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text, "tool_calls": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 80, "total_tokens": 120},
            }
        )


def start(port: int = 11435):
    srv = HTTPServer(("127.0.0.1", port), MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[mock] listening on http://127.0.0.1:{port}")
    return srv


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
    srv = start(port)
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
