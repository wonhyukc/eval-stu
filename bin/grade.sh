#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# 이메일 과제(0.x) 통합 고속 채점기 (grade.sh)
#
# 사용법:
#   ./bin/grade.sh <과제번호> [동작] [필터...]
#
# 주요 동작:
#   ./bin/grade.sh 0.5                  # [기본] 고속 채점 + CSV 저장 (미리보기, 시트/답장 X)
#   ./bin/grade.sh 0.5 sync             # 채점 결과 구글 시트 동기화
#   ./bin/grade.sh 0.5 reply            # 미답장 건만 핀포인트 자동 답장 발송
#   ./bin/grade.sh 0.5 all              # 원클릭 전체: 채점 + 시트 동기화 + 자동 답장
#
# 부분 타겟팅 필터:
#   ./bin/grade.sh 0.5 web1             # 특정 트랙만 (web1, web2, py)
#   ./bin/grade.sh 0.5 reply py         # 파이썬 반만 미답장 답장 발송
#   ./bin/grade.sh 0.5 --id 742         # 특정 학생 1명만 확인 (끝 3자리 또는 전체 학번)
#   ./bin/grade.sh 0.5 reply --id 742   # 특정 학생 1명에게만 답장 발송
# ────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${ROOT_DIR}/.venv/bin/python"
GRADER="${ROOT_DIR}/bin/extract_emails.py"

if [[ $# -eq 0 ]]; then
  cat <<'EOF'
📋 이메일 과제 통합 고속 채점기 (grade.sh)

사용법:
  ./bin/grade.sh <과제번호> [동작] [필터...]

동작 옵션:
  (생략)       : 채점 + CSV 저장 (시트 반영 X, 답장 발송 X, 안전 미리보기)
  sync         : 채점 결과 구글 시트 업로드 (Upsert)
  reply        : 미답장 메일에 대해서만 핀포인트 자동 답장 발송
  all          : 원클릭 전체: 채점 + 시트 업로드 + 자동 답장 발송

타겟팅 필터:
  py / web1 / web2   : 특정 트랙만 필터링
  --id <학번>        : 특정 학생만 필터링 (끝 3자리 또는 전체 학번)

예시:
  ./bin/grade.sh 0.5                   # 0.5 과제 전체 고속 채점 (5초)
  ./bin/grade.sh 0.5 sync              # 채점 결과 구글 시트에 반영
  ./bin/grade.sh 0.5 reply             # 미답장 학생들에게만 답장 발송
  ./bin/grade.sh 0.5 all               # 채점 + 시트 업로드 + 답장 원클릭 완료
  ./bin/grade.sh 0.5 web1              # 1반(web1)만 빠르게 채점
  ./bin/grade.sh 0.5 reply py          # 4반(파이썬) 미답장자만 답장 발송
  ./bin/grade.sh 0.5 reply --id 742    # 742 학생 1명만 확인 후 답장 발송
EOF
  exit 0
fi

TASK="$1"
shift

# 숫자만 입력한 경우 0. 접두 (예: 5 → 0.5)
if [[ "$TASK" =~ ^[0-9]+$ ]]; then
  TASK="0.${TASK}"
fi
WEEK="${TASK#0.}"

ACTION="crawl"
TRACKS=()
TARGET_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    sync)
      ACTION="sync"
      shift
      ;;
    reply)
      ACTION="reply"
      shift
      ;;
    all)
      ACTION="all"
      shift
      ;;
    py|web1|web2)
      TRACKS+=("$1")
      shift
      ;;
    --id|-i)
      TARGET_ID="$2"
      shift 2
      ;;
    *)
      TRACKS+=("$1")
      shift
      ;;
  esac
done

ARGS=("$WEEK")

if [[ ${#TRACKS[@]} -gt 0 ]]; then
  for t in "${TRACKS[@]}"; do
    ARGS+=("$t")
  done
fi

if [[ -n "$TARGET_ID" ]]; then
  ARGS+=("--id" "$TARGET_ID")
fi

case "$ACTION" in
  sync)
    # 기존 CSV 파일이 있으면 --from-csv 우선 확인
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

    # 만약 트랙/학번 필터가 없고 CSV가 존재하면 즉시 시트 업로드
    if [[ -n "$CSV_FILE" && ${#TRACKS[@]} -eq 0 && -z "$TARGET_ID" ]]; then
      echo "📄 기존 CSV 파일로 구글 시트 동기화: ${CSV_FILE}"
      "$PYTHON" "$GRADER" --from-csv "$CSV_FILE"
    else
      echo "📊 크롤링 및 구글 시트 동기화 시작..."
      "$PYTHON" "$GRADER" "${ARGS[@]}" --sync
    fi
    ;;
  reply)
    echo "✉️ 미답장 대상 핀포인트 답장 발송 시작..."
    "$PYTHON" "$GRADER" "${ARGS[@]}" --no-sheet --reply
    ;;
  all)
    echo "🚀 [원클릭 전체] 채점 + 구글 시트 동기화 + 자동 답장 발송 시작..."
    "$PYTHON" "$GRADER" "${ARGS[@]}" --all
    ;;
  crawl|*)
    echo "📧 과제 ${TASK} 고속 채점 시작 (미리보기/CSV 저장)..."
    "$PYTHON" "$GRADER" "${ARGS[@]}" --no-sheet
    ;;
esac
