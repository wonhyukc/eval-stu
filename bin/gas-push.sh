#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Pushing Apps Script for 1반 (web1) ==="
(cd "$SCRIPT_DIR/gas/web1" && npx -y @google/clasp push)

echo "=== Pushing Apps Script for 2반 (web2) ==="
(cd "$SCRIPT_DIR/gas/web2" && npx -y @google/clasp push)

echo "✅ All Apps Scripts pushed successfully."
