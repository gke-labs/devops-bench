#!/bin/bash
set -e

if [ -n "$GCP_SERVICE_ACCOUNT_KEY" ]; then
    echo "Authenticating with Service Account..."
    echo "$GCP_SERVICE_ACCOUNT_KEY" > /tmp/gcp_key.json
    gcloud auth activate-service-account --key-file=/tmp/gcp_key.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp_key.json
fi
