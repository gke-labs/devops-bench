# Image for running a CLI agent under test, isolated from the host.
#
# Contains the agent CLI and the cluster tooling a DevOps task needs, and
# deliberately nothing else. The host repo, the operator's home directory, the
# Docker socket and ADC are all absent by construction rather than by policy:
# they are simply not in this image and not mounted by the sandbox wrapper.
#
#   docker build -f hack/agent-sandbox.Dockerfile -t devops-bench/agent-sandbox:dev .
#
# Pin GEMINI_CLI_VERSION / OPENCLAW_VERSION for reproducible runs. Leaving
# either at "latest" means the agent under test changes underneath you between
# runs, which quietly makes results incomparable.
FROM node:22-slim

# OPENCLAW_VERSION / ANTHROPIC_VERTEX_PROVIDER_VERSION must be bumped together
# (they are a matched core+plugin pair; see the anthropic-vertex install step
# below). 2026.9.1-beta.1 is the earliest pairing confirmed live to actually
# work end-to-end for claude-fable-5 over anthropic-vertex:
#   - openclaw@2026.7.1 (npm "latest" at time of writing): the plugin's bundled
#     @anthropic-ai/vertex-sdk@0.19.0 + gaxios/google-auth-library combo throws
#     inside its JWT/gtoken token-exchange flow -- every run fails with
#     "Failed to acquire Google OAuth credentials" (openclaw/openclaw#107341,
#     fixed upstream by #108350).
#   - openclaw@2026.7.2-beta.7 (the first release carrying that fix): a
#     separate, unrelated bug -- the plugin's "activation": {"onStartup":
#     false} manifest flag makes `oc plugins list` (and the synthetic-auth
#     provider-ref discovery it shares code with) skip anthropic-vertex
#     entirely, so it never even reaches the ADC-detecting auth hook. Confirmed
#     live: `oc plugins list` omits the plugin altogether at this version.
#   - openclaw@2026.9.1-beta.1: the discovery bug above is fixed (`oc plugins
#     list` correctly shows `stock:anthropic-vertex/dist/index.js`), and this
#     is also the first version where the new per-agent SQLite auth-profile
#     store is fully wired for anthropic-vertex -- see
#     devops_bench/agents/cli/openclaw/agent.py's
#     `_needs_anthropic_vertex_auth_profile` for the runtime-side half of this
#     fix (the config-only `gcp-vertex-credentials` marker alone is no longer
#     sufficient on this version; an explicit `oc models auth paste-api-key`
#     profile registration is required too).
ARG KUBECTL_VERSION=v1.31.4
ARG GEMINI_CLI_VERSION=latest
ARG OPENCLAW_VERSION=2026.9.1-beta.1
ARG ANTHROPIC_VERTEX_PROVIDER_VERSION=2026.9.1-beta.1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl jq git less \
 && rm -rf /var/lib/apt/lists/*

# kubectl, matched to the architecture the image is built for so this works on
# both arm64 laptops and amd64 CI.
RUN arch="$(dpkg --print-architecture)" \
 && curl -fsSLo /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl" \
 && chmod 0755 /usr/local/bin/kubectl \
 && kubectl version --client=true >/dev/null

# Both agent CLIs the harness knows how to drive (devops_bench/agents/cli/):
# gemini_cli's native `gemini` binary, and openclaw's `oc` (the multi-model
# runner used for Claude/Vertex-backed agent-under-test runs). Installed
# system-wide so openclaw/agent.py's nvm-sourcing line in its bash command is
# a no-op here (Node/oc are already on PATH without it).
RUN npm install -g "@google/gemini-cli@${GEMINI_CLI_VERSION}" "openclaw@${OPENCLAW_VERSION}" \
 && npm cache clean --force

# openclaw's package.json registers its bin as `openclaw`, not `oc` -- the `oc`
# name is a convention this harness's own operator tooling relies on (see
# devops_bench/agents/cli/openclaw/agent.py's `_resolve_oc_bin`), not something
# npm sets up. Without this symlink `oc` resolves to nothing inside the image.
RUN ln -s "$(command -v openclaw)" /usr/local/bin/oc \
 && oc --version

# anthropic-vertex (Claude-on-Vertex models, e.g. claude-fable-5) is a
# separately-published plugin, not one of openclaw's own bundled "stock"
# plugins -- and `oc plugins install` registers it as a per-project USER
# plugin under ~/.openclaw/npm/projects/, a path that lives inside the very
# per-run OPENCLAW_STATE_DIR devops_bench isolates between runs (see
# agent.py's per-run oc config). A plugin registered there is invisible the
# moment the harness points oc at a fresh, empty state dir for the next run.
#
# The fix is to make it a stock plugin instead: physically place it under
# openclaw's own dist/extensions/, which oc always scans regardless of
# OPENCLAW_STATE_DIR. `npm install -g` into the SAME global prefix as
# openclaw (rather than `oc plugins install`'s isolated per-project install)
# is what makes this copy safe -- npm dedupes the "openclaw" peer dependency
# against the already-installed global package instead of vendoring its own
# node_modules/openclaw symlink, so there is no self-referencing symlink to
# trip openclaw's "Symlink escapes plugin root" guard or to recurse into
# when copied. Confirmed live: `oc plugins list` shows it as
# `stock:anthropic-vertex/dist/index.js`, enabled, under an isolated
# OPENCLAW_STATE_DIR, and its ESM entrypoint imports openclaw/plugin-sdk/*
# without error.
RUN npm install -g "@openclaw/anthropic-vertex-provider@${ANTHROPIC_VERTEX_PROVIDER_VERSION}" \
 && src="$(npm root -g)/@openclaw/anthropic-vertex-provider" \
 && dest="$(npm root -g)/openclaw/dist/extensions/anthropic-vertex" \
 && mkdir -p "${dest}" \
 && cp -a "${src}/." "${dest}/" \
 && npm uninstall -g "@openclaw/anthropic-vertex-provider" \
 && npm cache clean --force \
 && oc plugins list 2>&1 | grep -q "anthropic-vertex"

# The wrapper runs this container as the host user's uid:gid so files written to
# the mounted workspace are owned correctly. That uid does not exist in
# /etc/passwd, and some tooling resolves $HOME by looking the uid up rather than
# reading the env var, so give it a world-writable fallback. The wrapper also
# sets HOME=/workspace explicitly.
RUN mkdir -p /workspace /home/agent \
 && chmod 0777 /workspace /home/agent
ENV HOME=/workspace
WORKDIR /workspace

# No ENTRYPOINT on purpose: the sandbox wrapper appends the agent's own argv,
# which already begins with the binary name. An entrypoint here would silently
# prepend a second command.
CMD ["gemini", "--version"]
