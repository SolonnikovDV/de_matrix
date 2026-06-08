#!/usr/bin/env bash
# TIG context refresh for Cursor rules (preflight/postflight).
# Usage:
#   bash scripts/tig-context.sh [target] [base_ref]
#   bash scripts/tig-context.sh [target] [base_ref] --delta-only   # postflight fast path
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-.}"
BASE_REF="${2:-origin/main}"
EXTRA=()

if [[ "${3:-}" == "--delta-only" ]]; then
  EXTRA+=(--delta-only)
fi

if [[ "${TARGET}" != /* ]]; then
  TARGET="$(cd "${ROOT}/${TARGET}" && pwd)"
else
  TARGET="$(cd "${TARGET}" && pwd)"
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

if [[ ${#EXTRA[@]} -gt 0 ]]; then
  exec "${PY}" "${ROOT}/tig_app_ru.py" --cli \
    --target "${TARGET}" \
    --out "tig_snapshot.md" \
    --compact \
    --git-commits 12 \
    --reuse-if-unchanged \
    --delta \
    --delta-out "tig_delta.md" \
    --base-ref "${BASE_REF}" \
    --delta-log-commits 20 \
    --diff-max-lines 2500 \
    --index-max-entries 50 \
    "${EXTRA[@]}"
fi

exec "${PY}" "${ROOT}/tig_app_ru.py" --cli \
  --target "${TARGET}" \
  --out "tig_snapshot.md" \
  --compact \
  --git-commits 12 \
  --reuse-if-unchanged \
  --delta \
  --delta-out "tig_delta.md" \
  --base-ref "${BASE_REF}" \
  --delta-log-commits 20 \
  --diff-max-lines 2500 \
  --index-max-entries 50
