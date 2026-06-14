#!/usr/bin/env bash
# Sets up a local test environment: Ollama (gemma4:2b) + kind cluster.
# Intended to run as an environment setup script in Claude Code on the web,
# where its output is cached so subsequent sessions start ready.
set -euo pipefail

OLLAMA_VERSION="${OLLAMA_VERSION:-v0.30.8}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:2b}"
KIND_CLUSTER="${KIND_CLUSTER:-devops-bench}"

echo "==> Installing system deps"
apt-get update -qq
apt-get install -y -qq zstd

echo "==> Installing Ollama ${OLLAMA_VERSION}"
curl -fL "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst" \
  -o /tmp/ollama.tar.zst
tar --use-compress-program=unzstd -xf /tmp/ollama.tar.zst -C /usr/local/
rm /tmp/ollama.tar.zst
ollama --version

echo "==> Installing kind"
curl -fsSL "https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-linux-amd64" \
  -o /usr/local/bin/kind
chmod +x /usr/local/bin/kind
kind version

echo "==> Starting Docker daemon"
dockerd &>/tmp/dockerd.log &
DOCKERD_PID=$!
for i in $(seq 1 30); do
  [ -S /var/run/docker.sock ] && break
  sleep 1
done

echo "==> Pre-pulling kind node image (cached for future sessions)"
docker pull kindest/node:v1.36.1

echo "==> Creating kind cluster: ${KIND_CLUSTER}"
kind create cluster --name "${KIND_CLUSTER}" --wait 60s

echo "==> Starting Ollama server"
ollama serve &>/tmp/ollama.log &
for i in $(seq 1 30); do
  curl -sf http://localhost:11434/api/tags &>/dev/null && break
  sleep 1
done

echo "==> Pulling model: ${OLLAMA_MODEL}"
ollama pull "${OLLAMA_MODEL}"

echo ""
echo "Setup complete. To run the benchmark with Ollama + kind:"
echo "  export AGENT_PROVIDER=ollama JUDGE_PROVIDER=ollama"
echo "  export AGENT_MODEL=${OLLAMA_MODEL} JUDGE_MODEL=${OLLAMA_MODEL}"
echo "  export OLLAMA_BASE_URL=http://localhost:11434/v1"
