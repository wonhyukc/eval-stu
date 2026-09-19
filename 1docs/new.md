# 채점 체계 전면 개편 계획 (Type1/Type2 분리 및 정책 갱신)

> **작성일**: 2026-09-19
> **상태**: 계획 (Plan)
> **관련 이슈**: 아래 GitHub 이슈 참조

---

## 📸 배경 — 시트 현황 분석 (2반 스크린샷 기준)

현재 2반(web2) `score` 시트가 아래와 같이 **이미 수동으로 개편**되어 있음:

| 열 | 헤더 | 설명 | 비고 |
|:---:|:---:|---|---|
| A | `No` | 일련번호 (연속 증가) | |
| B | `wk` | 주차 | **신규 추가** |
| C~D | `ID` | 학번 (D열 숨김) | |
| E | `Score` | 점수 | |
| F | `Type1` | **대분류**: `hw`, `class`, `mid`, `fin` | **신규** |
| G | `Type2` | **세부유형**: `0.p`, `0.2`, `0.3` 등 (hw만) | **기존 Type → 이동** |
| H | `Reason` | 사유 | |
| I | `Date` | 날짜 | |
| J | `Name` | 이름 | |
| K | `Subject` | 메일 제목 | |

### Type1/Type2 매핑 규칙

| Type1 값 | Type2 값 | 설명 |
|:---:|:---:|---|
| `hw` | `0.p`, `0.1`, `0.2`, `0.3` 등 | 이메일 과제 (기존 `0.x` 번호) |
| `class` | *(빈칸)* | 수업참여 (help, presentation, answer, help others, focused 등) |
| `mid` | *(빈칸)* | 중간고사 |
| `fin` | *(빈칸)* | 기말고사 |

### 정렬 규칙

- **1차**: 주차(`wk`) 역순 (최근 주차가 위)
- **2차**: 학번(`ID`) 오름차순
- **번호(`No`)**: 정렬과 무관하게 계속 증가 (append-only increment)
- ⚠️ **현재 정렬은 손대지 않음** — 새로운 행 추가 시에만 이 정렬 규칙 적용

---

## 🔄 변경 사항 요약 (6개 항목)

### 1. 시트 헤더: `Type` → `Type1` + `Type2` 분리

**Before**: `No | StudentID | Track | Score | Type | Reason | Date | Name | Subject` (9열, A~I)
**After**: `No | wk | ID | (숨김) | Score | Type1 | Type2 | Reason | Date | Name | Subject` (11열, A~K)

- `Type1`: 4개 대분류 (`hw`, `class`, `mid`, `fin`)
- `Type2`: hw일 때만 과제 번호 (`0.x`), 나머지는 빈칸
- 수업참여(`class`)는 Type1에만 기록, Type2는 빈칸

### 2. 불필요한 행 제거 반영

- 시트에서 이미 수동으로 불필요 행이 제거됨
- 코드의 upsert 로직이 새 헤더 구조에 맞게 동작하도록 수정

### 3. 정렬 규칙 보존

- **기존 데이터의 정렬은 절대 변경하지 않음**
- 새 행 추가 시에만 정렬 규칙 적용: `wk 역순 → ID 오름차순`
- `No`는 지속 증가 (max_no + 1부터)

### 4. 미제출자 0점 등록

- **hw(이메일 과제)**: 해당 과제 미제출 학생을 찾아 Score=0, Type1=`hw`, Type2=`0.x`, Reason=`No submission` / `미제출`로 자동 등록
- 기존 `0.0점 → 시트 제외` 정책 **폐기** → **0점 행으로 시트에 등록**

### 5. 뒤늦은 제출 마감 변경

**Before**: 목 23:59 기준 + 15분 유예 → 48시간 이내 지각 인정 (토 23:59까지)

**After**: **다음 수업 시작 시각 전까지** 지각 인정

| 분반 | 수업 요일/시간 | 지각 마감 (다음 수업 시작 전) |
|:---:|---|---|
| **4반 (py)** | 월 09:00~11:50 | **다음 주 월요일 09:00 전** |
| **2반 (web2)** | 월 13:00~15:50 | **다음 주 월요일 13:00 전** |
| **1반 (web1)** | 월 16:00~18:45 | **다음 주 월요일 16:00 전** |

- 기존 목 23:59 + 15분 유예 → 정상 제출 기한은 유지
- **지각 인정 기한만 변경**: `48시간 이내(토 23:59)` → `다음 수업 시작 전`
- 48시간 초과 불인정 정책 → **다음 수업 시작 시각 초과 시 불인정(0점)**

### 6. 관련 문서·스킬·코드 전면 수정

변경이 필요한 파일 목록:

---

## 📋 수정 대상 파일 및 작업 항목

### Phase 1: 문서 (SSOT) 수정

| # | 파일 | 작업 |
|:---:|---|---|
| 1-1 | [`AGENTS.md`](file:///home/hyuk/prj/stu/eval-stu/AGENTS.md) | 헤더 정의에 `Type1`/`Type2` 반영, 지각 마감 정책 갱신, 0점 시트 등록 명시 |
| 1-2 | [`1docs/score-email.md`](file:///home/hyuk/prj/stu/eval-stu/1docs/score-email.md) | §2 배점표 Type1/Type2 분리, §3 지각 마감 → 다음 수업 시작 전, §6 헤더 갱신, 0점 시트 제외 → 등록으로 변경 |
| 1-3 | [`1docs/sheets.md`](file:///home/hyuk/prj/stu/eval-stu/1docs/sheets.md) | §3 시트 언어 정책 헤더 업데이트 (Type→Type1+Type2, wk 추가), §4.2 score 탭 스키마 갱신 |

### Phase 2: 스킬 수정

| # | 파일 | 작업 |
|:---:|---|---|
| 2-1 | [`.agents/skills/email-hw-grader/SKILL.md`](file:///home/hyuk/prj/stu/eval-stu/.agents/skills/email-hw-grader/SKILL.md) | 헤더 목록 → Type1/Type2 분리, 0점 시트 등록 방침, 지각 마감 갱신, upsert 키 변경 |

### Phase 3: 코드 수정

| # | 파일 | 작업 |
|:---:|---|---|
| 3-1 | [`modules/sheet_updater.py`](file:///home/hyuk/prj/stu/eval-stu/modules/sheet_updater.py) | **헤더/컬럼 인덱스 전면 재매핑** — 9열(A~I) → 11열(A~K), Type1/Type2 분리, wk 컬럼 추가, upsert 복합키 `(StudentID, Type1, Type2)`로 변경, range `A:I` → `A:K` |
| 3-2 | [`modules/grader.py`](file:///home/hyuk/prj/stu/eval-stu/modules/grader.py) | 채점 결과에 `type1`, `type2` 필드 분리, 미제출자 0점 행 생성 로직 추가 |
| 3-3 | [`modules/score_calculator.py`](file:///home/hyuk/prj/stu/eval-stu/modules/score_calculator.py) | 지각 마감 로직 → 다음 수업 시작 시각 기준으로 변경, type → type1/type2 분리 |
| 3-4 | [`settings.json`](file:///home/hyuk/prj/stu/eval-stu/settings.json) | 분반별 `late_deadline` 시각 추가 (`py: "09:00"`, `web2: "13:00"`, `web1: "16:00"`) |
| 3-5 | 관련 `bin/*.py` 스크립트들 | Type → Type1/Type2 분리에 따른 인덱스 조정 (영향 받는 스크립트 개별 확인 필요) |

### Phase 4: 검증

| # | 작업 |
|:---:|---|
| 4-1 | `./bin/harness-check.sh` 통과 확인 (Black, Flake8, Mypy, Pytest) |
| 4-2 | 기존 테스트 케이스 수정 및 통과 확인 |
| 4-3 | 실제 시트 데이터와 코드 컬럼 매핑 정합성 수동 검증 |

---

## ⚠️ 주의 사항 및 리스크

1. **시트 호환성**: 이미 시트가 수동으로 11열 구조로 변경됨 → 코드가 아직 9열(A~I) 기준이므로 **즉시 코드 수정 필요** (코드-시트 불일치 상태)
2. **Upsert 복합키 변경**: 기존 `(StudentID, Type)` → `(StudentID, Type1, Type2)` 변경 시 기존 데이터와의 키 매핑 호환성 확인 필요
3. **0점 등록**: 미제출자 판별을 위해 학생 명단 전체 vs 제출자 리스트 diff 로직 추가 필요
4. **심볼릭 링크 파일**: `1docs/sheets.md`, `1docs/scores.md`는 `../stu2603` 심볼릭 링크 → 수정 시 원본 저장소 측에서 수정해야 함
5. **K트랙(4반) 헤더**: 한글 헤더도 동일하게 `유형` → `유형1`/`유형2` 또는 `Type1`/`Type2`로 변경 필요 → **사용자 확인 필요**

---

## 🗓 실행 순서

```
Phase 1 (문서) → Phase 2 (스킬) → Phase 3 (코드) → Phase 4 (검증)
```

> [!IMPORTANT]
> 심볼릭 링크 파일(`1docs/sheets.md`)은 `../stu2603` 원본을 수정해야 합니다.
> K트랙 한글 헤더에서 Type1/Type2의 한글 표기를 확인해 주세요.
