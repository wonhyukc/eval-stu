# TIS 성적 입력 자동화 매뉴얼 (Playwright & Exbuilder API)

이 문서는 학교 종합정보시스템(TIS)의 성적 입력 페이지에 성적 데이터를 자동으로 입력하는 방법을 설명합니다. 시스템이 Exbuilder 프레임워크(Canvas/Grid 기반)를 사용하기 때문에 일반적인 DOM 탐색(예: `<input>` 태그 검색) 방식으로는 데이터를 입력할 수 없습니다. 대신, 브라우저의 원격 디버깅을 통해 Exbuilder 모델 API(`$builderScript`)에 직접 접근하여 값을 설정하는 방식을 사용합니다.

## 1. 사전 준비 (브라우저 디버깅 모드 실행)

스크립트가 기존에 열려 있는 브라우저를 제어하려면 Chrome을 **원격 디버깅 포트(9222)**를 열어 실행해야 합니다.

```bash
# 터미널에서 아래 명령어 실행 (경로는 환경에 맞게 조정)
google-chrome --remote-debugging-port=9222 --user-data-dir=/home/hyuk/.gemini/antigravity-browser-profile "https://tis.stu.ac.kr/" &
```

이후 TIS 포털에 로그인하여 **성적 입력 화면(cgdCRecInput)**을 띄워둡니다. 

## 2. 데이터 형식 준비

입력할 성적 데이터(학번, 중간, 기말, 과제, 출석 등)를 JSON, TSV, 혹은 스크립트 내 하드코딩된 문자열 형태로 준비합니다. 
> **중요:** 화면에 정렬된 학생 명단의 순서와 입력할 데이터의 순서가 완벽히 일치해야 가장 안전하고 빠르게 매핑할 수 있습니다. (혹은 학번 기준으로 `gradesMap`을 만들어 조회하는 방식을 사용합니다.)

## 3. 자동화 스크립트 핵심 원리 (Exbuilder API)

Playwright를 사용해 `http://127.0.0.1:9222`로 연결한 뒤, 대상 프레임(URL에 `cgdCRecInput` 포함)을 찾아 `evaluate()` 함수로 아래의 JavaScript 코드를 주입합니다.

```javascript
// 1. 그리드 모델 및 컨트롤 획득
const m = $builderScript["cgdCRecInputCtlID"].model;
const ctrl = m.getControl("rptCgdRecInput");

// 2. 총 행(Row) 개수 파악
const rowCount = ctrl.getRowCount();

// 3. 특정 셀의 값 읽기 (1-based index)
// Column 5: 학번 (STUD_NO)
const studentId = ctrl.getValue(rowIdx, 5).trim(); 

// 4. 특정 셀에 값 입력 (1-based index)
// 통상적으로 EVAL_SCR1(중간), EVAL_SCR2(기말), EVAL_SCR3(과제), EVAL_SCR4(출석) 등에 매핑됩니다.
ctrl.setCellVal(rowIdx, "EVAL_SCR1", scores.midterm);
ctrl.setCellVal(rowIdx, "EVAL_SCR2", scores.final);
ctrl.setCellVal(rowIdx, "EVAL_SCR3", scores.assignment);
ctrl.setCellVal(rowIdx, "EVAL_SCR4", scores.attendance);

// 5. 화면 갱신 (Redraw)
if (typeof ctrl.redraw === 'function') ctrl.redraw();
```

## 4. 파이썬 실행 스크립트 예시 (`tmp/input_all_grades2.py`)

미리 작성된 파이썬 스크립트(`/home/hyuk/prj/stu/eval/tmp/input_all_grades2.py` 참고)를 실행하면, 자동으로 브라우저 프레임에 연결하여 데이터를 주입합니다.

```bash
# 가상 환경에 Playwright가 설치되어 있어야 합니다.
source tmp/venv/bin/activate
python tmp/input_all_grades2.py
```

## 5. 실행 후 확인 사항
- 화면의 데이터가 정상적으로 기입되었는지 눈으로 확인합니다.
- 총 인원수(예: 23명)와 스크립트의 처리 인원수 로그(`matchedCount`)가 동일한지 대조합니다.
- 이상이 없으면 화면 우측 상단이나 하단의 **[저장]** 버튼을 직접 클릭하여 서버에 최종 제출합니다.
