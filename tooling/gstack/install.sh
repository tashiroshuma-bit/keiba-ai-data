#!/usr/bin/env bash
# Portable installer for gstack skills on a developer machine or persistent coding-agent host.
# This script does not install anything into the ChatGPT iOS app.
set -euo pipefail
HOST="${1:-codex}"
case "$HOST" in codex|claude|auto) ;; *) echo "Usage: bash install.sh [codex|claude|auto]" >&2; exit 2;; esac
command -v git >/dev/null || { echo "Git is required." >&2; exit 1; }
command -v bun >/dev/null || { echo "Bun is required (see gstack upstream prerequisites)." >&2; exit 1; }
INSTALL_DIR="${GSTACK_HOME:-$HOME/gstack}"
if [[ -e "$INSTALL_DIR" && ! -d "$INSTALL_DIR/.git" ]]; then
  echo "Refusing to overwrite a non-git directory: $INSTALL_DIR" >&2
  exit 1
fi
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git "$INSTALL_DIR"
else
  echo "Existing checkout detected; will not automatically update upstream code."
fi
(cd "$INSTALL_DIR" && ./setup --host "$HOST" && ./setup --status)
echo "gstack installed/configured for $HOST. Use the supported CLI, not the ChatGPT iOS UI, to invoke the skills."
