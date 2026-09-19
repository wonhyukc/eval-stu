#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Pulling Apps Script for 1반 (web1) ==="
(cd "$SCRIPT_DIR/gas/web1" && npx -y @google/clasp pull)

echo "=== Pulling Apps Script for 2반 (web2) ==="
(cd "$SCRIPT_DIR/gas/web2" && npx -y @google/clasp pull)

echo "✅ All Apps Scripts pulled successfully."
