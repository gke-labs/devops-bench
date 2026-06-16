#!/usr/bin/env bash
#
# Seeds a local bare git repository with the application manifests, so the agent
# can `git clone` it, migrate the deprecated APIs, and push the changes back —
# without depending on any cloud-hosted git service. Shared by both the kind and
# GKE stacks (portable across substrates).
#
# Env:
#   REPO_PATH      absolute path of the bare repo to create (e.g. $HOME/migration-repo.git)
#   MANIFESTS_DIR  directory containing the *.yaml manifests to seed
set -euo pipefail

REPO_PATH="${REPO_PATH:?REPO_PATH is required}"
MANIFESTS_DIR="${MANIFESTS_DIR:?MANIFESTS_DIR is required}"
REPO_PATH="${REPO_PATH/#\~/$HOME}"   # expand a leading ~ if present
# Resolve MANIFESTS_DIR to an absolute path now (callers pass it relative to the
# stack dir), since we `cd` into a temp dir before copying from it.
MANIFESTS_DIR="$(cd "${MANIFESTS_DIR}" && pwd)"

echo "==> Seeding manifests repo at ${REPO_PATH}"
rm -rf "${REPO_PATH}"
git init --bare "${REPO_PATH}"

WORK="$(mktemp -d)"
(
  cd "${WORK}"
  git init -q
  git config user.email "platform@example.com"
  git config user.name "Platform"
  cp "${MANIFESTS_DIR}"/*.yaml .
  git add .
  git commit -q -m "Add application manifests"
  git branch -M main
  git remote add origin "${REPO_PATH}"
  git push -q origin main
)
rm -rf "${WORK}"

# Point the bare repo's HEAD at main so a plain `git clone` checks it out
# (git init --bare defaults HEAD to the nonexistent 'master').
git -C "${REPO_PATH}" symbolic-ref HEAD refs/heads/main

echo "==> Repo seeded. Clone with: git clone ${REPO_PATH}"
