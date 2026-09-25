#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# 이메일 과제(0.x) 채점 래퍼
#   파이썬(4반) + 웹(1·2반) 두 트랙을 한 번에 실행
#
# 사용법:
#   ./bin/grade.sh 0.4          # 과제 0.4 양쪽 트랙 채점
#   ./bin/grade.sh 4            # 위와 동일 (0. 자동 접두)
# ────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${ROOT_DIR}/.venv/bin/python"
GRADER="${ROOT_DIR}/bin/extract_grades.py"

# ── 인자 없으면 사용법 출력 ──
if [[ $# -eq 0 ]]; then
  cat <<'EOF'
📋 이메일 과제 채점 스크립트 (grade.sh)

사용법:
  ./bin/grade.sh <과제번호>

예시:
  ./bin/grade.sh 0.4      # 과제 0.4 채점 (py + web 두 트랙)
  ./bin/grade.sh 4        # 위와 동일 (0. 자동 접두)
  ./bin/grade.sh 0.a      # 10주차 과제 채점

실행 순서:
  1) 파이썬 4반 (K트랙, 한글)  →  구글시트 자동 기록
  2) 웹 1·2반 (E트랙, 영문)    →  구글시트 자동 기록
EOF
  exit 0
fi

TASK="$1"

# 숫자만 입력한 경우 0. 접두 (예: 4 → 0.4)
if [[ "$TASK" =~ ^[0-9]+$ ]]; then
  TASK="0.${TASK}"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  📧 과제 ${TASK} 채점 시작"
echo "═══════════════════════════════════════════════"

# ── 1) 파이썬 4반 (K트랙 · 한글) ──
echo ""
echo "── [1/2] 파이썬 4반 (K트랙, 한글) ──"
"$PYTHON" "$GRADER" --course py --query "$TASK" --lang ko

# ── 2) 웹 1·2반 (E트랙 · 영문, 자동 분반 라우팅) ──
echo ""
echo "── [2/2] 웹 1·2반 (E트랙, 영문) ──"
"$PYTHON" "$GRADER" --course web --query "$TASK" --lang en

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ 과제 ${TASK} 채점 완료 (py + web)"
echo "═══════════════════════════════════════════════"
