#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/third_party/kubetest2"

if [ ! -d "$REPO_DIR" ]; then
  echo "Cloning kubetest2..."
  git clone https://github.com/kubernetes-sigs/kubetest2 "$REPO_DIR"
else
  echo "kubetest2 already cloned."
fi

cd "$REPO_DIR"

echo "Building kubetest2..."
make install

echo "Building kubetest2-gke..."
make install-deployer-gke

echo "Setup complete. Binaries are in $REPO_DIR/bin"
