#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# 이메일 과제(0.x) 채점 래퍼
#
# 사용법:
#   ./bin/grade.sh 0.4          # 크롤링 + CSV 저장
#   ./bin/grade.sh 0.4 sync     # CSV → 구글 시트 업로드
#   ./bin/grade.sh 0.4 sort     # 구글 시트 정렬
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
  ./bin/grade.sh <과제번호>           # 1단계: Gmail 크롤링 → CSV 저장
  ./bin/grade.sh <과제번호> sync      # 2단계: CSV → 구글 시트 업로드
  ./bin/grade.sh <과제번호> sort      # 3단계: 구글 시트 정렬 (주차↓ 학번↑)

예시:
  ./bin/grade.sh 0.4                 # Gmail에서 메일 수집 + 채점 → CSV
  ./bin/grade.sh 4                   # 위와 동일 (0. 자동 접두)
  ./bin/grade.sh 0.4 sync            # CSV 확인 후 시트에 반영
  ./bin/grade.sh 0.4 sort            # py 시트 정렬 (주차 역순 + 학번)
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

if [[ "$ACTION" == "sort" ]]; then
  # ── 3단계: 구글 시트 정렬 ──
  echo ""
  echo "═══════════════════════════════════════════════"
  echo "  🔄 구글 시트 정렬 (주차 역순 → 학번 오름차순)"
  echo "═══════════════════════════════════════════════"
  echo ""

  "$PYTHON" -c "
from modules.sheet_updater import sort_sheet_remote
# py 시트
sort_sheet_remote(course='py')
"

elif [[ "$ACTION" == "sync" ]]; then
  # ── 2단계: CSV → 구글 시트 ──
  CSV_FILE=""
  for candidate in \
    "${ROOT_DIR}/output/mail$(printf '%02d' "$WEEK" 2>/dev/null || echo "$WEEK").csv" \
    "${ROOT_DIR}/output/mail${WEEK}.csv" \
    "${ROOT_DIR}/9output/grades_output_${WEEK}_py.csv"; do
    if [[ -f "$candidate" ]]; then
      CSV_FILE="$candidate"
      break
    fi
  done

  echo ""
  echo "═══════════════════════════════════════════════"
  echo "  📊 과제 ${TASK} → 구글 시트 동기화"
  echo "═══════════════════════════════════════════════"
  echo ""

  if [[ -z "$CSV_FILE" ]]; then
    echo "❌ CSV 파일을 찾을 수 없습니다."
    echo "   검색 경로: output/mail${WEEK}.csv, 9output/grades_output_${WEEK}_py.csv"
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
