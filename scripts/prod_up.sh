#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Backward-compatible alias for unified startup entrypoint.
bash "${ROOT_DIR}/scripts/up.sh"
