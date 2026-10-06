#!/bin/bash
# tmp 디렉터리 내의 파일 중 수정한 지 3일(72시간)이 지난 파일을 안전하게 삭제합니다.
# 프로젝트 루트를 기준으로 실행되도록 보장
cd "$(dirname "$0")/.." || exit 1

TMP_DIR="tmp"

if [ ! -d "$TMP_DIR" ]; then
    echo "⚠️ $TMP_DIR 디렉터리가 존재하지 않습니다."
    exit 0
fi

echo "🧹 $TMP_DIR 디렉터리 정리를 시작합니다. (수정일 기준 3일 초과 파일 삭제)"

# -mtime +2: 정확히는 2*24=48시간 이상 지난 시점부터 매칭하지만, 통상적으로 3일 이전 파일을 의미
# 파일 삭제
find "$TMP_DIR" -type f -mtime +2 -print -delete
# 빈 디렉터리 삭제 (최상위 tmp 폴더 자체는 -mindepth 1로 보호)
find "$TMP_DIR" -mindepth 1 -type d -empty -print -delete

echo "✅ 정리가 완료되었습니다. (최근 3일 이내의 파일 보존)"
