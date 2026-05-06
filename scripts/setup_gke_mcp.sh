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

if command -v npm &> /dev/null && npm --version &> /dev/null; then
  echo "Installing UI dependencies..."
  npm --prefix ui install

  echo "Building UI..."
  npm --prefix ui run build
else
  echo "Warning: npm CLI not found in PATH. Skipping GKE MCP UI dashboard build."
fi

if command -v go &> /dev/null && go version &> /dev/null && command -v npm &> /dev/null && npm --version &> /dev/null; then
  echo "Building gke-mcp..."
  go build -o gke-mcp .
  echo "Setup complete. Binary is at $REPO_DIR/gke-mcp"
else
  echo "Warning: go compiler or npm not found in PATH. Skipping gke-mcp binary compilation as it requires pre-built UI assets."
fi

# --- Gemini CLI Extension Setup ---
if command -v gemini &> /dev/null; then
  echo "Configuring Gemini CLI settings..."
  mkdir -p "$HOME/.gemini"
  python3 -c "
import json, os
path = os.path.expanduser('~/.gemini/settings.json')
data = {}
if os.path.exists(path):
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except Exception:
        pass
if 'security' not in data: data['security'] = {}
if 'auth' not in data['security']: data['security']['auth'] = {}
if 'selectedType' not in data['security']['auth']:
    data['security']['auth']['selectedType'] = 'gemini-api-key'
    print('Configured gemini-api-key auth selection in settings.json.')
else:
    print('Authentication already configured in settings.json, leaving untouched.')
if 'general' not in data: data['general'] = {}
if 'sessionRetention' not in data['general']:
    data['general']['sessionRetention'] = {'enabled': True, 'maxAge': '30d', 'warningAcknowledged': True}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"

  echo "Installing GKE MCP extension in Gemini CLI..."
  gemini extensions install https://github.com/GoogleCloudPlatform/gke-mcp.git --consent

  echo "Configuring GKE MCP extension trust overrides..."
  mkdir -p "$HOME/.gemini/extensions"
  python3 -c "
import json, os
path = os.path.expanduser('~/.gemini/extensions/extension-enablement.json')
data = {}
if os.path.exists(path):
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except Exception:
        pass
if 'gke-mcp' not in data:
    data['gke-mcp'] = {'overrides': ['*']}
    print('Configured GKE MCP trust overrides.')
else:
    overrides = data['gke-mcp'].get('overrides', [])
    if '*' not in overrides:
        overrides.append('*')
        data['gke-mcp']['overrides'] = overrides
        print('Appended * to GKE MCP trust overrides.')
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"
  echo "Gemini CLI GKE MCP extension configured successfully!"
else
  echo "Warning: gemini CLI not found in PATH. Skipping extension setup."
fi
