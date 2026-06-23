FROM python:3.11-slim

# Install system dependencies
# ARCH selects the OpenTofu archive (pass --build-arg ARCH=amd64|arm64). It
# defaults to the build host's native architecture via dpkg, so the bundled tofu
# matches the image and runs without emulation (e.g. on an arm64 podman machine).
ARG ARCH
ARG TOFU_VERSION=1.8.8
RUN apt-get update && apt-get install -y \
    git \
    make \
    curl \
    wget \
    gnupg \
    unzip \
    lsb-release \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs \
    && ARCH="${ARCH:-$(dpkg --print-architecture)}" \
    && wget "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_${ARCH}.zip" \
    && unzip "tofu_${TOFU_VERSION}_linux_${ARCH}.zip" -d /usr/local/bin/ \
    && rm "tofu_${TOFU_VERSION}_linux_${ARCH}.zip" \
    && rm -rf /var/lib/apt/lists/*



# Install Gemini CLI globally (customizable version)
ARG GEMINI_CLI_VERSION=latest
RUN npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION}

# Install Go (required to build kubetest2)
COPY --from=golang:1.22 /usr/local/go/ /usr/local/go/
ENV PATH="/usr/local/go/bin:${PATH}"

# Install Google Cloud SDK and kubectl
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update && apt-get install -y \
    google-cloud-cli \
    google-cloud-cli-gke-gcloud-auth-plugin \
    kubectl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the codebase
COPY . .

# Build kubetest2
ARG KUBETEST2_VERSION=master
RUN bash ./scripts/setup_kubetest2.sh "$KUBETEST2_VERSION"

# Build gke-mcp and configure Gemini CLI extension
ARG GKE_MCP_VERSION=main
RUN bash ./scripts/setup_gke_mcp.sh "$GKE_MCP_VERSION"

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create a results directory
RUN mkdir -p /app/results

# Set up entrypoint
RUN chmod +x /app/scripts/entrypoint.sh
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
