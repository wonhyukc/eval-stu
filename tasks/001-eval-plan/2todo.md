# [2todo] 채점 관리 시스템 고도화 및 지각 처리 파이프라인

- [ ] 1. 과목별 마감일 설정 파일(SSOT) 생성
  - Target: `tasks/001-eval-plan/deadlines.json` 
  - Action: 파이썬, 웹1, 웹2의 주차별 마감일 및 감점 기준이 담긴 JSON 생성
  - Validation: 정상 포맷 확인

- [ ] 2. 채점 스크립트에 '제출 시간(Timestamp)' 파싱 및 0점/감점 로직 추가
  - Target: `bin/check_evaluations.py`
  - Action: Timestamp를 `deadlines.json`의 마감일과 비교하여 지각인 경우 점수를 0점 처리하는 분기문 작성
  - Validation: `--week 10` 실행 시 마감일 초과자가 지각으로 판별되어 0점 처리되는지 확인

- [ ] 3. 구글 시트 쓰기 권한 추가 및 채점 결과 자동 업로드 (Auto-Append) 기능 추가
  - Target: `bin/check_evaluations.py`
  - Action: `SCOPES`에 쓰기 권한을 추가(`https://www.googleapis.com/auth/spreadsheets`)하고, 로컬 CSV로 저장한 결과를 지정된 구글 시트(예: "결과취합" 탭)의 최하단에 `append` 하도록 Google Sheets API 연동 구현.
  - Validation: 스크립트 실행 후 실제 구글 시트 하단에 새로운 결과 행이 추가되었는지 육안 확인 (중복 채점 시 계속 누적되는지 확인)

- [ ] 4. 시트 본문 내 채점 상태(대기/완료) 업데이트 기능 추가 (선택)
  - Target: `bin/check_evaluations.py`
  - Action: 채점 완료된 행의 상태 컬럼을 업데이트
