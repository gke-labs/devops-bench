#!/usr/bin/env bash
# Installs Ollama and pulls the model used for local end-to-end testing.
set -euo pipefail

MODEL="${OLLAMA_MODEL:-gemma4:2b}"

if ! command -v ollama &>/dev/null; then
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "Starting Ollama server in the background..."
ollama serve &>/tmp/ollama.log &
OLLAMA_PID=$!

# Wait for Ollama to be ready
for i in $(seq 1 30); do
  if curl -sf http://localhost:11434/api/tags &>/dev/null; then
    break
  fi
  sleep 1
done

echo "Pulling model: ${MODEL}"
ollama pull "${MODEL}"

echo ""
echo "Ollama is running (PID ${OLLAMA_PID}) with model ${MODEL}."
echo ""
echo "To run the benchmark locally with Ollama, set:"
echo "  export AGENT_PROVIDER=ollama"
echo "  export JUDGE_PROVIDER=ollama"
echo "  export AGENT_MODEL=${MODEL}"
echo "  export JUDGE_MODEL=${MODEL}"
echo "  export OLLAMA_BASE_URL=http://localhost:11434/v1  # default, can omit"
