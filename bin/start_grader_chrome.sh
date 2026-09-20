#!/usr/bin/env bash
# start_grader_chrome.sh — 전용 Chrome 백그라운드 기동 헬퍼
# 메인 크롬(~/.config/google-chrome)과 완전 격리된 채점 전용 프로필 사용
# AGENTS.md: "크롬 자동화 시 메인 브라우저 무간섭 및 전용 프로필 운영 원칙"

set -euo pipefail

GRADER_DATA_DIR="$HOME/.config/eval-stu-grader"
CDP_PORT="${CDP_PORT:-9222}"

# 이미 실행 중인지 확인
if curl -s "http://localhost:${CDP_PORT}/json/version" >/dev/null 2>&1; then
    echo "✅ 전용 Chrome이 이미 실행 중입니다 (CDP port ${CDP_PORT})"
    exit 0
fi

# 전용 디렉터리 생성 (최초 1회)
mkdir -p "$GRADER_DATA_DIR"

echo "🚀 전용 Chrome 백그라운드 기동 중... (user-data-dir: $GRADER_DATA_DIR)"
google-chrome \
    --user-data-dir="$GRADER_DATA_DIR" \
    --profile-directory="Default" \
    --remote-debugging-port="${CDP_PORT}" \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-networking \
    --disable-sync \
    --headless=new \
    &>/dev/null &

# CDP 포트가 열릴 때까지 최대 30초 대기
for i in $(seq 1 30); do
    if curl -s "http://localhost:${CDP_PORT}/json/version" >/dev/null 2>&1; then
        echo "✅ 전용 Chrome 준비 완료 (PID: $!, CDP port: ${CDP_PORT})"
        exit 0
    fi
    sleep 1
done

echo "❌ 전용 Chrome 시작 시간 초과 (30초)"
exit 1
