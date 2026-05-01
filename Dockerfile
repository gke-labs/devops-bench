FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    make \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

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
RUN bash ./scripts/setup_kubetest2.sh

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create a results directory
RUN mkdir -p /app/results

# Set up entrypoint
RUN chmod +x /app/scripts/entrypoint.sh
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
