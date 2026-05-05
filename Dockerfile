FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    make \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
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

# Build gke-mcp
ARG GKE_MCP_VERSION=main
RUN bash ./scripts/setup_gke_mcp.sh "$GKE_MCP_VERSION"

# Pre-configure Gemini CLI to bypass interactive authentication wizard on startup
RUN mkdir -p /root/.gemini && \
    echo '{"security":{"auth":{"selectedType":"gemini-api-key"}},"general":{"sessionRetention":{"enabled":true,"maxAge":"30d","warningAcknowledged":true}}}' > /root/.gemini/settings.json

# Pre-install GKE MCP extension in Gemini CLI
RUN gemini extensions install https://github.com/GoogleCloudPlatform/gke-mcp.git --consent

# Trust all directories (including /app) for the GKE MCP extension to ensure it loads in the container workdir
RUN echo '{"gke-mcp":{"overrides":["*"]}}' > /root/.gemini/extensions/extension-enablement.json

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create a results directory
RUN mkdir -p /app/results

# Set up entrypoint
RUN chmod +x /app/scripts/entrypoint.sh
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
