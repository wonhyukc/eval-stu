#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# 이메일 과제(0.x) 채점 래퍼
#
# 사용법:
#   ./bin/grade.sh 0.4          # 크롤링 + CSV 저장 (시트 X)
#   ./bin/grade.sh 0.4 sync     # CSV → 구글 시트 업로드
# ────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${ROOT_DIR}/.venv/bin/python"
GRADER="${ROOT_DIR}/bin/extract_emails.py"
OUTPUT_DIR="${ROOT_DIR}/9output"

# ── 인자 없으면 사용법 출력 ──
if [[ $# -eq 0 ]]; then
  cat <<'EOF'
📋 이메일 과제 채점 스크립트 (grade.sh)

사용법:
  ./bin/grade.sh <과제번호>           # 1단계: Gmail 크롤링 → CSV 저장
  ./bin/grade.sh <과제번호> sync      # 2단계: CSV → 구글 시트 업로드

예시:
  ./bin/grade.sh 0.4                 # Gmail에서 메일 수집 + 채점 → CSV
  ./bin/grade.sh 4                   # 위와 동일 (0. 자동 접두)
  ./bin/grade.sh 0.4 sync            # CSV 확인 후 시트에 반영

흐름:
  1단계) 크롬이 열리고 Gmail 검색 → 채점 → 9output/ 에 CSV 저장
  2단계) CSV를 확인·수정한 뒤 sync로 구글 시트에 반영
EOF
  exit 0
fi

TASK="$1"
ACTION="${2:-crawl}"

# 숫자만 입력한 경우 0. 접두 (예: 4 → 0.4)
if [[ "$TASK" =~ ^[0-9]+$ ]]; then
  TASK="0.${TASK}"
fi

# 0.4 → 4  (주차 번호만 추출)
WEEK="${TASK#0.}"

if [[ "$ACTION" == "sync" ]]; then
  # ── 2단계: CSV → 구글 시트 ──
  CSV_FILE="${OUTPUT_DIR}/grades_output_${WEEK}_py.csv"

  echo ""
  echo "═══════════════════════════════════════════════"
  echo "  📊 과제 ${TASK} → 구글 시트 동기화"
  echo "═══════════════════════════════════════════════"
  echo ""

  if [[ ! -f "$CSV_FILE" ]]; then
    echo "❌ CSV 파일이 없습니다: ${CSV_FILE}"
    echo "   먼저 ./bin/grade.sh ${TASK} 로 크롤링하세요."
    exit 1
  fi

  echo "📄 CSV 파일: ${CSV_FILE}"
  echo "── 내용 미리보기 ──"
  head -5 "$CSV_FILE"
  echo "..."
  echo ""

  "$PYTHON" "$GRADER" --from-csv "$CSV_FILE"
else
  # ── 1단계: 크롤링 + CSV 저장 (시트 업로드 안 함) ──
  echo ""
  echo "═══════════════════════════════════════════════"
  echo "  📧 과제 ${TASK} 크롤링 시작 (Playwright)"
  echo "═══════════════════════════════════════════════"
  echo ""

  "$PYTHON" "$GRADER" "$WEEK" --no-sheet
fi
