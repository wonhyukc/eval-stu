#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# 이메일 과제(0.x) 채점 래퍼
#   Playwright로 Gmail UI에서 메일을 수집하고 채점 + 시트 기록
#
# 사용법:
#   ./bin/grade.sh 0.4          # 과제 0.4 채점
#   ./bin/grade.sh 4            # 위와 동일 (0. 자동 접두)
# ────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${ROOT_DIR}/.venv/bin/python"
GRADER="${ROOT_DIR}/bin/extract_emails.py"

# ── 인자 없으면 사용법 출력 ──
if [[ $# -eq 0 ]]; then
  cat <<'EOF'
📋 이메일 과제 채점 스크립트 (grade.sh)

사용법:
  ./bin/grade.sh <과제번호>

예시:
  ./bin/grade.sh 0.4      # 과제 0.4 채점 (Playwright → 시트 기록)
  ./bin/grade.sh 4        # 위와 동일 (0. 자동 접두)
  ./bin/grade.sh 0.a      # 10주차 과제 채점

동작:
  1) 크롬 브라우저가 열리며 Gmail에서 메일 검색·수집
  2) 학생별 채점 후 구글 스프레드시트에 자동 기록
EOF
  exit 0
fi

TASK="$1"

# 숫자만 입력한 경우 0. 접두 (예: 4 → 0.4)
if [[ "$TASK" =~ ^[0-9]+$ ]]; then
  TASK="0.${TASK}"
fi

# 0.4 → 4  (주차 번호만 추출)
WEEK="${TASK#0.}"

echo ""
echo "═══════════════════════════════════════════════"
echo "  📧 과제 ${TASK} 채점 시작 (Playwright)"
echo "═══════════════════════════════════════════════"
echo ""

"$PYTHON" "$GRADER" "$WEEK"
