#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/third_party/gke-mcp"
VERSION="${1:-main}"

if [ ! -d "$REPO_DIR" ]; then
  echo "Cloning gke-mcp (version: $VERSION)..."
  git clone https://github.com/GoogleCloudPlatform/gke-mcp "$REPO_DIR"
else
  echo "gke-mcp already cloned."
fi

cd "$REPO_DIR"
git fetch origin
git checkout "$VERSION"

echo "Installing UI dependencies..."
npm --prefix ui install

echo "Building UI..."
npm --prefix ui run build

echo "Building gke-mcp..."
go build -o gke-mcp .

echo "Setup complete. Binary is at $REPO_DIR/gke-mcp"

# --- Gemini CLI Extension Setup ---
if command -v gemini &> /dev/null; then
  echo "Pre-configuring Gemini CLI settings..."
  mkdir -p "$HOME/.gemini"
  echo '{"security":{"auth":{"selectedType":"gemini-api-key"}},"general":{"sessionRetention":{"enabled":true,"maxAge":"30d","warningAcknowledged":true}}}' > "$HOME/.gemini/settings.json"

  echo "Installing GKE MCP extension in Gemini CLI..."
  gemini extensions install https://github.com/GoogleCloudPlatform/gke-mcp.git --consent

  echo "Configuring extension directory trust overrides..."
  mkdir -p "$HOME/.gemini/extensions"
  echo '{"gke-mcp":{"overrides":["*"]}}' > "$HOME/.gemini/extensions/extension-enablement.json"
  echo "Gemini CLI GKE MCP extension configured successfully!"
else
  echo "Warning: gemini CLI not found in PATH. Skipping extension setup."
fi
