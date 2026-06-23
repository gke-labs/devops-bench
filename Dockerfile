# syntax=docker/dockerfile:1
#
# Full eval-harness image for the `devops_bench` pipeline. Installs the packaged
# `devops-bench` console script and runs the end-to-end harness
# (devops_bench.run / devops_bench.cli). Requires Python >=3.12 to match
# pyproject's requires-python.
#
# Installs what the pipeline drives at runtime: OpenTofu (the sole provisioning
# engine), kubectl, the Google Cloud SDK, the Gemini CLI, and the GKE MCP server.
# Builds natively on amd64 and arm64 (e.g. an Apple-silicon `podman machine`):
# the OpenTofu archive is chosen from the ARCH build arg, which defaults to the
# build host's native arch.
#
# Build (Podman or Docker are interchangeable). ARCH defaults to the native arch,
# so a plain build "just works"; override it only when building for another arch:
#   podman build -t devops-bench-harness:latest .
#   podman build --build-arg ARCH=arm64 -t devops-bench-harness:latest .
#
# Run the full pipeline over a task (no cloud infra; uses the NoOpDeployer):
#   podman run --rm \
#     -v "$(pwd)/results:/app/results" \
#     -e JUDGE_PROVIDER=ollama -e JUDGE_MODEL=llama3 \
#     devops-bench-harness:latest tasks/gcp/create-deployment/task.yaml --no-infra

FROM python:3.12-slim

# Install system dependencies + Node.js (for the Gemini CLI) and OpenTofu.
# OpenTofu ships per-arch archives; ARCH selects which one to download. It is a
# build arg (pass --build-arg ARCH=amd64|arm64) and defaults to the build host's
# native architecture via dpkg, so the binary always matches the image and runs
# without emulation. Keep ARCH consistent with any --platform you build for.
ARG ARCH
ARG TOFU_VERSION=1.8.8
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    unzip \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && ARCH="${ARCH:-$(dpkg --print-architecture)}" \
    && wget -q "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_${ARCH}.zip" \
    && unzip "tofu_${TOFU_VERSION}_linux_${ARCH}.zip" -d /usr/local/bin/ \
    && rm "tofu_${TOFU_VERSION}_linux_${ARCH}.zip" \
    && rm -rf /var/lib/apt/lists/*

# Install Gemini CLI globally (customizable version)
ARG GEMINI_CLI_VERSION=latest
RUN npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION}

# Install the GKE MCP server via the official installer. It downloads a prebuilt,
# arch-matched binary to /usr/local/bin, so `gke-mcp` is on PATH for the agent's
# MCP capability / Gemini CLI to launch.
RUN curl -sSL https://raw.githubusercontent.com/GoogleCloudPlatform/gke-mcp/main/install.sh | bash

# Install Google Cloud SDK and kubectl (apt repo serves both amd64 and arm64).
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    google-cloud-cli \
    google-cloud-cli-gke-gcloud-auth-plugin \
    kubectl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the codebase
COPY . .

# Install the package (and every provider SDK) from pyproject. This exposes the
# `devops-bench` console script and the importable `devops_bench` package.
RUN pip install --no-cache-dir ".[all]"

# Create a results directory for the bind mount
RUN mkdir -p /app/results

# Bootstrap auth/env, then exec the harness CLI.
RUN chmod +x /app/scripts/entrypoint_harness.sh
ENTRYPOINT ["/app/scripts/entrypoint_harness.sh"]
