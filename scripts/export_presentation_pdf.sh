#!/usr/bin/env bash
# Export presentation HTML to PDF (A4 landscape) via Chrome/Chromium headless.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HTML="${1:-$ROOT/presentations/middle_de_competency_matrix.html}"
PDF="${2:-${HTML%.html}.pdf}"
HTML_URI="file://${HTML}"

browser=""
for candidate in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium" \
  "google-chrome" \
  "chromium" \
  "chromium-browser"; do
  if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
    browser="$candidate"
    break
  fi
done

if [[ -z "$browser" ]]; then
  echo "Chrome/Chromium not found. Open in browser and Print → Save as PDF:" >&2
  echo "  $HTML" >&2
  exit 1
fi

"$browser" \
  --headless=new \
  --disable-gpu \
  --no-pdf-header-footer \
  --print-to-pdf="$PDF" \
  "$HTML_URI"

echo "PDF written: $PDF"
