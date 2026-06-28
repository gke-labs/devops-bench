#!/bin/bash
#
# Entrypoint for the full eval-harness image (Dockerfile).
#
# Bootstraps optional cloud auth and a writable KUBECONFIG, then execs the
# `devops-bench` CLI. Arguments passed to `podman run`/`docker run`
# after the image name are forwarded verbatim to the CLI, e.g.:
#
#   podman run ... devops-bench-harness:latest tasks/noop/create-deployment/task.yaml --no-infra
#
# If no positional task source is given, BENCH_SOURCE (or the legacy
# BENCH_TASK_FILE) is used so the image is also drivable purely via env vars.
set -e

# Optional cloud auth (service-account key via env, mounted ADC, etc.).
if [ -n "$CLOUD_PROVIDER" ]; then
    AUTH_SCRIPT="./scripts/setup_auth_${CLOUD_PROVIDER}.sh"
    if [ -f "$AUTH_SCRIPT" ]; then
        # shellcheck source=/dev/null
        source "$AUTH_SCRIPT"
    fi
fi

# Bypass any host-level GKE API endpoint overrides mounted via gcloud config.
export CLOUDSDK_API_ENDPOINT_OVERRIDES_CONTAINER="https://container.googleapis.com/"

# Use a writable kubeconfig inside the container.
export KUBECONFIG="${KUBECONFIG:-/tmp/kubeconfig}"

# Forward CLI args if given; otherwise fall back to env-provided task source.
if [ "$#" -eq 0 ]; then
    SOURCE="${BENCH_SOURCE:-$BENCH_TASK_FILE}"
    if [ -z "$SOURCE" ]; then
        echo "Error: no task source given. Pass one as an argument, e.g." >&2
        echo "  podman run ... devops-bench-harness:latest <task.yaml> [--no-infra]" >&2
        echo "or set BENCH_SOURCE / BENCH_TASK_FILE." >&2
        exit 2
    fi
    set -- "$SOURCE"
fi

echo "Starting DevOps-bench eval harness..."
exec devops-bench "$@"
