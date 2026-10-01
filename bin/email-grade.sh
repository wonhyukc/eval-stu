#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# 이메일 과제(0.x) 자동 채점 실행 래퍼 (email-grade.sh)
#
# 프로젝트의 .venv 가상환경 파이썬을 자동으로 감지하여
# auto_grade_email.py에 모든 인자를 전달합니다.
# ────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"

# 1. .venv 가상환경 인터프리터 존재 여부 확인
if [[ -x "$VENV_PYTHON" ]]; then
  PYTHON="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "❌ 파이썬 인터프리터를 찾을 수 없습니다 (.venv 또는 python3 필요)" >&2
  exit 1
fi

# 2. auto_grade_email.py 실행 (전달받은 모든 인자 그대로 pass-through)
exec "$PYTHON" "${SCRIPT_DIR}/auto_grade_email.py" "$@"
