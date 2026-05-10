# [2todo] 채점 관리 시스템 고도화 및 지각 처리 파이프라인

- [ ] 1. 과목별 마감일 설정 파일(SSOT) 생성
  - Target: `tasks/001-eval-lan/deadlines.json` 
  - Action: 파이썬, 웹1, 웹2의 주차별 마감일(`YYYY-MM-DD HH:MM:SS` 형식) 및 감점률(0점 처리 또는 비율 감점) 구조체를 정의한 JSON 파일 생성
  - Validation: `cat tasks/001-eval-lan/deadlines.json` 실행 시 정상 JSON 형태 확인
- [ ] 2. 채점 스크립트에 '제출 시간(Timestamp)' 파싱 로직 추가
  - Target: `bin/check_evaluations.py`
  - Action: 구글 시트 첫 번째 컬럼(보통 Timestamp)을 파싱하여 datetime 객체로 변환하는 로직 추가
  - Validation: 스크립트 실행 시 각 제출 건의 Timestamp가 정상적으로 인식되어 터미널에 출력되는지 확인
- [ ] 3. 과목별 마감일 대조 및 지각 감점/0점 처리 로직 구현
  - Target: `bin/check_evaluations.py`
  - Action: 파싱된 Timestamp와 `deadlines.json`의 마감일을 대조. 지각인 경우 점수를 0점 처리하거나 명시된 감점률을 적용하는 분기문 작성
  - Validation: `--week 10` 실행 시 마감일 초과자가 로그에 '지각(Late) - 0점 처리' 등으로 출력되고 최종 CSV 점수에 반영되는지 확인
- [ ] 4. 구글 시트 쓰기(Write) 권한 활성화 및 상태 업데이트 기능 추가 (선택/심화)
  - Target: `bin/check_evaluations.py`
  - Action: 채점이 완료된 행의 '채점 상태' 컬럼에 `완료` 도장을 찍어주는 구글 시트 API 업데이트 로직 구현 (또는 상태 관리용 로컬 DB 기록)
  - Validation: 스크립트 실행 후 구글 시트에 실제 상태값이 기록되는지 확인
