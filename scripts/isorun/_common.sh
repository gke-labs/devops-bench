#!/usr/bin/env bash
# Shared library for scripts/isorun/*.sh. Source this, don't execute it.
# shellcheck disable=SC2034  # REPO/PROJECT/CLUSTER/REGION are consumed by the scripts that source this file

REPO="/Users/eric.hole/dev/gke-labs/devops-bench/.claude/worktrees/agent-stumping-thesis-ba2147"

PROJECT="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
CLUSTER="${GKE_CLUSTER_NAME:-autopilot-cluster-1}"
REGION="${REGION:-us-central1}"

# Unsets every *_API_KEY env var so the agent/judge fall through to Vertex ADC.
_iso_unset_keys() {
  unset -v GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_CLOUD_API_KEY \
    ANTHROPIC_API_KEY OPENAI_API_KEY AGENT_API_KEY
}

# Exports the Vertex-ADC env for the gemini CLI agent (BENCH_AGENT_TYPE=gemini).
iso_auth_gemini() {
  _iso_unset_keys

  export JUDGE_PROVIDER="google-vertex"
  export JUDGE_MODEL="${JUDGE_MODEL:-gemini-3.1-pro-preview}"
  export GCP_PROJECT_ID="$PROJECT"
  export GCP_VERTEX_LOCATION="global"

  export GOOGLE_GENAI_USE_VERTEXAI="true"
  export GOOGLE_CLOUD_PROJECT="$PROJECT"
  export GOOGLE_CLOUD_LOCATION="global"

  export BENCH_AGENT_TYPE="gemini"
  export AGENT_TARGET="gemini"
  export AGENT_PROVIDER="google-vertex"
  export AGENT_MODEL="${AGENT_MODEL:-gemini-3.5-flash}"
  export BENCH_USE_MCP="false"
}

# Exports the Vertex-ADC env for the openclaw (oc) CLI agent.
iso_auth_oc() {
  _iso_unset_keys

  export JUDGE_PROVIDER="google-vertex"
  export JUDGE_MODEL="${JUDGE_MODEL:-gemini-3.1-pro-preview}"
  export GCP_PROJECT_ID="$PROJECT"
  export GCP_VERTEX_LOCATION="global"

  export GOOGLE_GENAI_USE_VERTEXAI="true"
  export GOOGLE_CLOUD_PROJECT="$PROJECT"
  export GOOGLE_CLOUD_LOCATION="global"

  export BENCH_AGENT_TYPE="openclaw"
  export AGENT_TARGET="$HOME/bin/oc"
  export AGENT_PROVIDER="google-vertex"
  export AGENT_MODEL="${AGENT_MODEL:-gemini-3.5-flash}"
  # oc's Vertex-ADC marker; bare `oc` reads this instead of a real API key.
  export GOOGLE_CLOUD_API_KEY="gcp-vertex-credentials"
  export BENCH_USE_MCP="false"

  echo "note: oc may still need 'oc exec-policy preset yolo' before it will run tool calls unattended." >&2
}

# Makes a fresh scratch workspace outside $REPO and prints its path.
iso_stage_ws() {
  mktemp -d -t dvb-iso.XXXX
}

# Aborts unless the ambient kubectl context corresponds to $1 (the CLUSTER
# this run intends to seed/grade). Call before any cleanup or seed step: a
# context mismatch means seeding one cluster and grading another, silently.
#
# GKE contexts are named gke_PROJECT_REGIONORZONE_CLUSTER (four underscore-
# delimited fields: literal "gke", then project id, then region or zone, then
# cluster name). GCP project ids and GKE cluster names cannot themselves
# contain underscores (RFC1035 / GCP naming rules), so splitting on "_" is
# unambiguous; match on the trailing cluster-name component rather than
# requiring exact equality against the whole context string.
#
# kind contexts are named kind-CLUSTER (see tf/modules/cluster/kind/main.tf),
# so a leading "kind-" is stripped the same way; CLUSTER itself is the bare
# cluster name in that case, not a kind-prefixed one. Only an exact "kind-"
# prefix is stripped (not a bare substring match), so e.g. ctx "my-cluster-2"
# with expected "my-cluster" still correctly falls through to the mismatch
# check below rather than passing.
iso_verify_cluster_context() {
  local expected="$1"
  local ctx
  ctx="$(kubectl config current-context 2>/dev/null || true)"
  if [[ -z "$ctx" ]]; then
    echo "ABORT: no active kubectl context (kubectl config current-context returned nothing). Point kubeconfig at the cluster named '$expected' before running." >&2
    exit 1
  fi

  local ctx_cluster="$ctx"
  if [[ "$ctx" == gke_* ]]; then
    ctx_cluster="${ctx#gke_*_*_}"
  elif [[ "$ctx" == kind-* ]]; then
    ctx_cluster="${ctx#kind-}"
  fi

  if [[ "$ctx_cluster" != "$expected" ]]; then
    echo "ABORT: kubectl context '$ctx' (cluster component: '$ctx_cluster') does not match CLUSTER='$expected'. Switch context with 'kubectl config use-context', or fix CLUSTER, before running: seeding/grading against the wrong cluster produces a meaningless result." >&2
    exit 1
  fi
}
