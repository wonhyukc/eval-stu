#!/usr/bin/env bash
# stop_grader_chrome.sh — 전용 Chrome만 안전하게 종료 (메인 크롬 무간섭)
set -euo pipefail

CDP_PORT="${CDP_PORT:-9222}"
GRADER_DATA_DIR="$HOME/.config/eval-stu-grader"

# 전용 프로필의 Chrome PID만 찾아서 종료
pids=$(pgrep -f "user-data-dir=${GRADER_DATA_DIR}" 2>/dev/null || true)
if [ -n "$pids" ]; then
    echo "🛑 전용 Chrome 종료 중 (PIDs: $pids)"
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 2
    # 여전히 살아있으면 강제 종료
    remaining=$(pgrep -f "user-data-dir=${GRADER_DATA_DIR}" 2>/dev/null || true)
    if [ -n "$remaining" ]; then
        echo "$remaining" | xargs kill -9 2>/dev/null || true
    fi
    echo "✅ 전용 Chrome 종료 완료"
else
    echo "ℹ️ 전용 Chrome이 실행 중이지 않습니다"
fi
