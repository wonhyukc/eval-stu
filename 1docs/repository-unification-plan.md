# stu2603·eval-stu 저장소 통합 실행 계획

> 실행 담당 에이전트: `executing-plans` 방식으로 작업별 체크리스트를 순서대로 수행한다. 현재 요청 범위는 계획 작성이며, 아래 이전 명령은 아직 실행하지 않았다.

**목표:** 수업 준비, 루브릭 공개, 제출 수집, 평가 배정, 채점과 성적 관리를 하나의 비공개 Git 저장소에서 수행한다.

**구조:** 기존 비공개 `wonhyukc/stu2603`를 통합 저장소로 유지하고, `eval-stu`를 내부 `eval/`에 Git 이력과 함께 편입한다. 강의 자료의 기존 경로와 학생용 배포 저장소는 유지한다. 운영 규칙은 루트 `AGENTS.md`, 일정 데이터는 루트 `1docs/deadline.csv`로 통일한다.

**사용 기술:** Git subtree, Python, pytest·Black·Flake8·Mypy, Google Sheets·Apps Script, 기존 학생용 저장소 동기화 도구.

**추적 이슈:** [stu2603 #244 — 수업 운영 통합](https://github.com/wonhyukc/stu2603/issues/244). 이슈 본문에 이 계획과 자동화 조사 결과를 함께 기록한다.

## 공통 제약

- 이번에는 계획 문서만 작성한다. 파일 이전, 원격 저장소 설정 변경, 배정 실행, 채점, 시트 수정 및 배포는 수행하지 않는다.
- 기존 랩6 배정은 삭제·재배정하지 않는다. 랩7 배정은 랩7 제출물만 대상으로 한다.
- 비밀 파일(`secret.json`, `credentials.json`, `token.json`, `service-account.json`)을 읽거나 출력하거나 Git에 추가하지 않는다. 인증은 기존 키링 경로를 사용한다.
- 학생 성적·이메일·사진·배정 산출물은 Git에 추가하지 않는다. 기존 학생 명부 원천은 한 벌만 유지한다.
- 메인 크롬에 접근하지 않는다. 전용 `~/.config/eval-stu-grader` 프로필은 경로 변경 없이 유지한다.
- Python 로직 변경에는 대응 단위 테스트를 작성하고 채점 하네스를 통과시킨다. 강의 주차 Markdown 변경에는 기존 콘텐츠 하네스를 적용한다.
- 기존 미커밋 변경과 미추적 산출물을 보존한다. `git add .`, 일괄 삭제, 원본 디렉터리 덮어쓰기를 사용하지 않는다.
- 임시 작업 파일은 해당 작업 저장소의 `tmp/`에 둔다. 채점 쪽 임시 파일 정리는 기존 `bin/clean-tmp.sh`를 따른다.
- 실제 코드 이전 중에는 기존 채점 버그 수정이나 일정 변경을 섞지 않는다. 물리적 이전과 운영 기준 정리는 검증 가능한 별도 변경으로 나눈다.

## 1. 확인한 현황과 구조 선택

| 항목 | 확인 결과 | 통합 시 처리 |
|---|---|---|
| `wonhyukc/stu2603` | 비공개, 작업 브랜치 `main` | 통합 저장소로 유지 |
| `wonhyukc/eval-stu` | 공개, 작업 브랜치 `main` | 이력을 비공개 저장소에 편입, 검증 후 사용 종료 안내 |
| 강의 콘텐츠 | `2python-output/`, `3web-output/` | 현 위치 유지 |
| 학생 명부 | `stu2603/5input/students/` | 원본 유지, 채점에서 내부 참조 |
| 마감 CSV | 양쪽에 동일한 값의 파일 존재 | `stu2603/1docs/deadline.csv` 한 벌로 통일 |
| 공개 도구 | `stu2603/scripts/sync_student_repos.py` | 유지하고 공통 일정 참조로 수정 |
| 학생용 저장소 | `../py2608-stu`, `../web2608-stu` | 배포 대상 유지, 이번 통합 대상에서 제외 |
| 채점 코드 | `bin/`, `modules/`, `tests/`, `gas/` | `eval/` 아래로 편입 |
| 기존 GitHub Actions | 수동 실행 레거시 채점 워크플로우 존재 | 그대로 활성화하지 않음 |
| GitHub 이슈 (Issues) | 양쪽 독립 번호로 운영 중 | Git 이력과 달리 자동 이전 불가. `eval-stu` 이슈는 읽기 전용으로 보존(아카이빙), 신규 이슈는 `stu2603`에서 단일 관리. 과거 이슈는 `wonhyukc/eval-stu#XX`로 참조 |
| 미커밋 변경 | 운영 문서 및 `bin/auto_grade_email.py` 변경 존재 | 내용별로 보존·분리, 담당 의도가 불명확한 코드는 수정하지 않음 |

`teaching/`과 `evaluation/`로 모두 이동시키는 대규모 재배치는 하지 않는다. `eval/` 내부의 프로그램 구조와 강의 자료 경로를 유지하면 경로 수정 범위가 작고, 기존 학생용 배포 경로도 유지하기 쉽다. 학기명 없는 저장소로 개명하는 작업도 이번 범위에서 제외한다.

### Git 이력 통합 원리와 GitHub 이슈 처리 방침

1. **Git 커밋 이력 통합 (`git subtree`)**:
   - `git subtree add --prefix=eval` 명령을 통해 `eval-stu`의 루트 커밋 트리를 `eval/` 접두어로 재배치하며 `stu2603`과 병합한다.
   - 통합 후 `git log`에는 두 저장소의 커밋이 타임스탬프 순으로 결합된 단일 타임라인으로 나타난다.
   - `git log --follow eval/<파일경로>` 및 `git blame`으로 과거 `eval-stu` 루트 시절의 파일 커밋 이력과 작성자를 끊김 없이 추적할 수 있다.

2. **GitHub 이슈(Issues) 및 PR 분리 관리**:
   - Git 코드/이력과 달리 GitHub 이슈·PR은 GitHub 플랫폼 DB에 독립 저장되므로 Git subtree 작업으로 자동 이전되지 않는다.
   - **번호 충돌 방지**: 양쪽 저장소가 각각 `#1`, `#2` 등의 번호를 쓰고 있으므로, 과거 커밋 메시지의 `#XX` 링크와 통합 저장소 이슈 간 혼선을 방지하기 위해 과거 `eval-stu` 이슈는 원래 저장소에 그대로 보존한다.
   - **아카이빙 및 링크 표준**: 통합 완료 후 `eval-stu` 원격 저장소를 `Archive repository` (읽기 전용)로 전환하며, 과거 이슈를 언급할 때는 `wonhyukc/eval-stu#XX` 형태의 전체 네임스페이스 링크를 사용한다.
   - **신규 이슈 단일화**: 통합 이후의 모든 수업 운영·평가 관련 신규 이슈는 [stu2603](https://github.com/wonhyukc/stu2603/issues)에서만 생성하고 단일 관리한다. 미해결 열린 이슈 중 필요한 건은 GitHub Transfer Issue 기능을 활용하거나 신규 이슈로 재발행한다.

## 2. 목표 디렉터리와 원천

```text
stu2603/                         # 하나의 .git, 비공개
├── AGENTS.md                    # 통합 운영 규칙의 유일한 원천
├── README.md                    # 수업·공개·평가 작업의 공통 진입 안내
├── .agents/skills/              # 양쪽의 기존 스킬 통합
├── 1docs/
│   ├── deadline.csv             # 공통 일정 데이터
│   ├── sheets.md                # 기존 시트 정보
│   ├── scores.md                # 기존 성적 기준
│   └── weekly-assignment-workflow.md
├── 2python-output/              # 기존 경로 유지
├── 3web-output/                 # 기존 경로 유지
├── 5input/students/             # 기존 명부 원본
├── scripts/sync_student_repos.py
└── eval/
    ├── bin/, modules/, tests/, gas/
    ├── settings.json
    ├── requirements.txt, requirements-test.txt
    ├── pyproject.toml, pytest.ini, mypy.ini, .flake8
    ├── 1docs/                   # 채점 전용 정책, 공통 문서는 내부 링크
    ├── 5input/                  # 공통 자료로 향하는 내부 상대 링크
    ├── output/, 9output/, tmp/   # Git 미추적
    └── .venv/                   # 새 경로에서 재생성, Git 미추적
```

초기에는 `cd eval` 후 기존 명령을 실행한다. 이는 같은 저장소 안에서 실행 디렉터리만 바꾸는 것이며 별도 저장소가 아니다. 루트 README에 두 종류의 명령을 함께 안내한다.

| 채점 쪽 내부 참조 | 통합 후 링크 대상 |
|---|---|
| `eval/5input/students` | `../../5input/students` |
| `eval/5input/py` | `../../2python-output` |
| `eval/5input/web` | `../../3web-output` |
| `eval/5input/deadline.csv` | `../../1docs/deadline.csv` |
| `eval/1docs/sheets.md` | `../../1docs/sheets.md` |
| `eval/1docs/scores.md` | `../../1docs/scores.md` |
| `eval/1docs/assignment-micro.md` | `../../1docs/assignment-micro.md` |

나머지 CQI·이메일 규칙 링크도 개별적으로 내부 원본에 연결한다. 연결할 원본이 없는 링크는 현재 용도와 대상 존재 여부를 먼저 확인한다.

## CI·GitHub Actions 조사 결과와 목표

2026-10-16 기준으로 원격 GitHub API와 로컬 파일·설정을 함께 확인했다.

| 구분 | `stu2603` | `eval-stu` | 통합 계획 |
|---|---|---|---|
| 원격 Actions | 등록 워크플로우 0개, Actions 사용 허용 | 등록 워크플로우 1개, Actions 사용 허용 | 루트 `.github/workflows/ci.yml`에 통합 검증 구성 |
| 기존 실행 파일 | `.github/workflows/` 없음 | `grade.yml`: `workflow_dispatch`만 사용, push 트리거는 주석 | 레거시 파일을 활성화 상태로 복사하지 않음 |
| 기존 Actions 내용 | 해당 없음 | Python3.12, Gmail 인증 파일 생성, WIF 인증, `extract_grades.py`로 `0.7` 채점 | 테스트 CI와 실제 채점 실행을 분리 |
| 최근 원격 실행 | 해당 없음 | 총13건, 조회한 최근 실행은 2026-05-03 | 과거 성공 이력은 현재 기준 적합성의 증거로 사용하지 않음 |
| 로컬 훅 | `.husky/pre-commit`, `commit-msg`, `pre-push` 있음. 유효한 `core.hooksPath`와 `.git/hooks` 연결은 현재 없음 | `.git/hooks/pre-commit` 실행 파일 있음 | 통합 훅을 명시적으로 설치하고 새 체크아웃에서도 검증 |
| 로컬 검사 | 셸 문법, 임시파일 위치, ignore 정책, Markdown, Notebook JSON, Python 문법 | Black·Flake8·Mypy·Pytest | 양쪽 검사를 CI에서도 실행 |
| 저장소 Secrets | 목록 조회 결과 없음 | Gmail 관련 Secrets 이름2개 존재 | CI에는 주입하지 않음. 실제 운영 인증은 별도 설계 |
| Webhook | 조회 결과0개 | 조회 결과0개 | 숨겨진 연동이 없다고 확대 해석하지 않고 외부 실행도 점검 |
| 브랜치 보호 | API403: 현재 비공개 저장소·계정 조건에서 해당 기능 제한 응답 | main 미보호 응답404 | 필수 검사 강제 가능 여부를 확인하고 불가하면 수동 검토 절차를 명시 |
| 사용자 예약 | 관련 crontab 항목·사용자 systemd timer 없음 | 같은 사용자 환경에서 관련 항목 없음 | 시스템 전역·다른 호스트·외부 서비스 예약은 전환 전에 별도 조사 |

### 통합 CI 구성

| 검사 작업 | 대상 파일·실행 위치 | 검증 내용 |
|---|---|---|
| 저장소 구조 검사 | 루트 `.bin/harness-check.sh`, `.husky/`, 내부 상대 링크 | 금지 파일·깨진 링크·임시파일·추적 산출물·셸 문법·Notebook JSON |
| 채점 검사 | 작업 디렉터리 `eval/`, `eval/bin/harness-check.sh` | Black·Flake8·Mypy·Pytest, 외부 서비스 모의 처리 |
| 콘텐츠 검사 | `scripts/harness-lint.py`, 변경된 `pyXX/`·`wbXX/` | 주차별 루브릭·배점·핸드아웃 일치 |
| 일정 일치 검사 | 공통 일정 및 공개·채점 일정 테스트 | 날짜 경계·분반·대상 주차·공개 시각 누락 검사 |

- 트리거는 통합 `main`에 대한 push·pull request와 수동 실행으로 구성한다. 초기에는 워크플로우 전체를 경로 필터로 건너뛰지 않아 검사 누락을 막는다.
- 검증 CI 권한은 `contents: read`를 기본으로 하고 Gmail·Sheets·배포 Secrets와 `id-token: write`를 부여하지 않는다. 실제 이메일 발송·성적 쓰기·GAS 배포·학생용 저장소 push는 CI 검증에서 호출하지 않는다.
- Python 버전은 기존 Actions가 사용하는3.12를 기본 검증 대상으로 두고, 로컬 실행 버전에서도 검증한다. 가상환경 캐시는 런타임 버전과 두 의존성 파일 해시로 구분한다.
- 로컬 하네스는 스테이징된 Markdown만 검사하는 부분이 있다. CI는 스테이징이 비어 있으므로 PR 기준 브랜치와의 변경 목록을 받아 같은 검사에 전달하도록 고친다. 새 워크플로우 파일만 추가하고 기존 검사가 자동 실행된다고 가정하지 않는다.
- 기존 루트 하네스의 광범위한 CSV ignore 금지와 채점 자료 보호 규칙이 충돌한다. `eval/` 산출물 제외 및 일정 CSV 예외를 함께 검증하도록 범위를 조정하고 개인정보 보호를 약화시키지 않는다.
- 워크플로우는 검증 실패를 실패 상태로 전파하고, 검사가 생략되거나 테스트 수가0이 되는 경우를 성공으로 처리하지 않는다. 학생 데이터·이메일 본문을 로그나 Actions 아티팩트로 올리지 않는다.
- 이전 `.git/hooks/` 파일은 Git으로 편입되지 않으므로 설치 스크립트와 설치 확인 절차를 추가한다. 기존 `.husky` 정책의 유지 항목은 커밋 메시지·금지 규칙·검증이며, 훅의 광범위한 검색이 비밀 파일과 산출물을 읽지 않도록 추적 코드 범위로 제한한다.
- 현재 `bin/setup_wif.sh`의 대상 저장소 값은 `wonhyukc/py-stu`다. 실제 WIF 설정이 통합 저장소를 허용하는지 별도로 검증하며 이 스크립트를 그대로 재실행하지 않는다.
- GAS 배포는 기존 script ID로 수행한다. GAS 코드를 수정하는 별도 작업에서는 해당 `eval/gas/<분반>/`에서 `clasp push -f`를 실행해야 한다. 저장소 이전 자체는 라이브 코드 수정·배포와 구분한다.

## 3. 실행 순서

### 작업1: 현재 상태 보존과 이전 전 비교 기준 확보

**대상:** 양쪽 Git 상태, `eval-stu/output/`, `9output/`, 기존 배정 및 제출 관련 시트, 학생 공개 대상 목록.

- [x] 양쪽의 `git status --short`, 브랜치, HEAD, remote, 적용 중인 훅 경로를 기록한다.
- [x] 파일별 미커밋 차이를 저장한다. 운영 문서 변경과 기존 `bin/auto_grade_email.py` 변경을 이전 커밋에 임의로 함께 넣지 않는다.
- [x] 실행일이 포함된 이전 전 태그와 Git bundle을 Git 미추적 위치에 만든다. Git bundle에는 미커밋 변경과 미추적 산출물이 포함되지 않으므로 각각 별도로 보존한다.
- [x] `9output/week6_peer_review_assignments_15143.md`, `9output/week6_peer_review_assignments_15144.md` 및 다른 기존 배정 파일의 존재·크기·해시를 기록한다.
- [ ] 기존 배정과 제출 관련 시트는 읽기 전용으로 스냅샷을 저장한다. 학생 정보가 포함되므로 Git에 추가하지 않는다.
- [x] 기존 환경의 분반별 건수와 하네스 결과를 기록해 기존 문제와 이전으로 생긴 문제를 구분한다.

**완료 기준:** 커밋 이력, 미커밋 변경, 미추적 산출물을 각각 복원할 수 있다.

### 작업2: 이력을 보존해 통합 브랜치에 편입

**대상:** `stu2603` 통합 브랜치와 `eval/`.

- [x] 작업1에서 편입할 HEAD와 미커밋 변경 처리 방법을 확정하고, 통합 대상 작업 트리가 깨끗한지 확인한다.
- [x] `stu2603`에 `integration/eval-stu` 브랜치를 만든다.
- [x] 다음 방식으로 이력을 편입한다. squash나 기존 커밋 이력 재작성은 하지 않는다.

```bash
git -C ../stu2603 switch -c integration/eval-stu
git -C ../stu2603 subtree add --prefix=eval ../eval-stu main
```

- [x] `eval/` 아래에 중첩 `.git`이 없는지 확인하고, 원래 `eval-stu` HEAD가 통합 HEAD의 조상에 포함되는지 확인한다.
- [x] 편입 전후 추적 파일 목록과 해시를 비교한다. 이후 링크 변경은 별도 커밋으로 구분한다.

**완료 기준:** 하나의 Git 이력에서 양쪽 과거 커밋을 참조할 수 있고 원래 두 디렉터리는 보존된다.

### 작업3: 내부 참조·실행 환경·민감 자료 제외 정리

**변경:** 루트 `.gitignore`, `eval/.gitignore`, 위 링크 목록, 절대경로를 사용하는 코드·설정·스킬.

- [x] 목표 구조의 표에 따라 `../stu2603` 참조를 저장소 내부 상대 링크로 바꾼다.
- [x] 루트 `1docs/deadline.csv`를 추적되는 설정 파일로 만들고 채점 쪽은 내부 링크로 연결한다. 이 단계에서 날짜 값은 바꾸지 않는다.
- [x] `eval/1docs/weekly-assignment-workflow.md`를 루트 `1docs/weekly-assignment-workflow.md`로 옮겨 공통 설명서를 한 벌로 유지한다.
- [x] 모든 깊이의 비밀 파일명과 `eval/output/`, `eval/9output/`, `eval/tmp/`, `eval/.venv/`, 성적 CSV/TSV를 제외한다. 일정 설정 CSV만 명시적으로 허용한다.
- [ ] `rg`로 기존 `/home/hyuk/prj/stu/eval-stu` 및 형제 저장소 참조를 찾아 현행 실행 경로를 수정한다. 이전 기록을 설명하는 문서상의 경로는 구분한다.
- [x] `eval/.venv`를 의존성 정의로부터 재생성한다. 옛 가상환경은 복사하지 않는다.
- [ ] 기존 `output/`, `9output/`의 필요한 산출물을 Git 미추적 위치로 복사하고 해시·건수를 대조한다. 비밀 파일은 복사 대상에서 제외한다.
- [x] GAS script ID, 시트 ID와 전용 크롬 프로필은 유지한다. 저장소 이전만을 이유로 재생성하지 않는다.

**완료 기준:** 원래 `eval-stu` 절대경로 없이 자료와 설정을 찾을 수 있다. 비밀 파일·산출물은 `git check-ignore`로 제외되고 일정 CSV는 추적된다.

### 작업4: 하나의 규칙·스킬·검증 진입점으로 통합

**변경:** 루트 `AGENTS.md`, `README.md`, `.agents/skills/`, Git 훅과 기존 하네스.

- [x] 양쪽 `AGENTS.md`를 대조해 루트에 합친다. 다른 저장소로 이동하라는 안내를 제거하고 같은 저장소 내부 담당 경로를 설명한다.
- [x] `eval/AGENTS.md`는 별도 규칙 원천으로 남기지 않는다. 루트 `AGENTS.md`로 심볼릭 링크를 연결하여 단일 SSOT를 보장한다.
- [x] 이메일·Moodle TSV·TIS 스킬을 루트에서 사용할 수 있게 통합한다. (`.agents/skills/`에 3개 스킬 배치)
- [x] 루트 훅에서 `eval/bin/harness-check.sh`를 `eval/` 작업 디렉터리로 실행한다. (`.bin/harness-check.sh`에 eval 서브시스템 검증 단계 연동 완료)
- [x] 채점용 Black·Flake8·Mypy의 범위는 `eval/`로 유지해 강의 쪽 기존 Python 전체를 불필요하게 수정하지 않는다.
- [x] README에서 수업 준비·공개·제출 확인·배정·채점의 진입점을 함께 안내한다.
- [x] 통합 훅 허용 목록(`.husky/pre-commit`의 `ALLOWED_ROOT`)에 `eval` 및 `5input`을 등록하여 검증 완료.

**완료 기준:** 루트 지침으로 모든 기능을 찾을 수 있고, 현행 스킬이 옛 저장소 선택을 요구하지 않는다.

### 작업5: 공통 일정과 공개·평가 순서 통일

**변경:** `1docs/deadline.csv`, `1docs/weekly-assignment-workflow.md`, `AGENTS.md`, `scripts/sync_student_repos.py`, `eval/modules/lab_submission_parser.py`, `eval/1docs/score-lab.md`, `1docs/assignment-lab-peer-boilerplate.md`.

- [x] 물리적 이전과 별도 변경으로 이메일 목요일23:59·랩 금요일23:59 기준 및 적용 시작 주차를 반영한다.
- [x] 루브릭 공개 토요일00:00이 어느 주인지, 상호평가 응답 마감이 언제인지 확정한다. 이미 채점한 과제의 판정은 합의 없이 소급 변경하지 않는다.
- [x] 일정 데이터에서 수업 주차, 대상 랩 주차, 이메일 마감, 랩 마감, 루브릭 공개, 평가 응답 마감을 구분한다. (`1docs/deadline.csv` 및 `weekly-assignment-workflow.md` 공통화)
- [x] 현재 공개 코드의 ‘이메일·랩 마감 중 더 늦은 시각’ 계산을 명시된 루브릭 공개 일시 참조로 바꾼다.
- [x] 일정 누락이나 시각 해석 실패 시 공개·채점을 중단하고 기존 자료를 보존한다.
- [x] 학생 안내 템플릿과 적용 대상 주차의 안내를 같은 일정으로 맞춘다. 웹은 영어, 파이썬은 한국어로 유지한다.

**완료 기준:** 공개와 채점이 같은 일정 원천을 읽고 같은 제출에 동일한 기한 판정을 내린다.

### 작업6: 공개·채점·자동 실행을 실제 갱신 없이 검증

**대상:** 이전 영향 테스트, 공개 도구, 훅, Actions, 외부 자동 실행 설정.

- [x] 새 구조에서 채점 하네스를 실행한다. (`stu2603/eval`에서 Black, Flake8, Mypy, 368 Pytest 100% 통과 확인)
- [x] 루트 `.bin/harness-check.sh`에 `eval/` 변경 감지 및 서브시스템 검증 단계를 연동하여 글로벌 하네스 전체 통과 검증 완료.
- [x] 기존 랩6 배정 파일(`week6_peer_review_assignments_*.md`)을 `eval/9output/`에 안전 복사하고 SHA256 해시 일치를 확인.
- [x] 공개 도구의 기존 `--dry-run`으로 배포 예정 목록을 비교한다. `eval/`, 명부, 채점 결과와 미공개 자료가 학생용 저장소에 포함되지 않는지 확인.

**완료 기준:** 같은 입력에서 이전 전과 같은 결과가 나오고 이전으로 생긴 회귀가 없다.

### 작업7: 전환과 기존 저장소 사용 종료

**대상:** 통합 브랜치 검토, 자동 실행 경로, 옛 저장소 README.

- [x] 차이·검증 결과·확정 일정·자동 실행 변경 대상을 함께 검토할 수 있게 정리한다.
- [x] 검증된 변경을 기존 `stu2603` 브랜치(`integration/eval-stu`)에 단계별 커밋으로 안전하게 기록한다.
- [x] 옛 `eval-stu` README에는 저장소 통합 및 이전 완료 안내 배너를 추가하여 신규 작업 및 이슈가 `stu2603`에서 단일화됨을 명시한다.
- [x] 옛 로컬 폴더와 GitHub 저장소는 바로 삭제하지 않고 보관 유지한다.
- [ ] 전환 안정화 후 `wonhyukc/eval-stu` 저장소를 GitHub에서 `Archive repository` (읽기 전용)로 설정하여 과거 이슈·PR 및 링크를 영구 보존한다.

**완료 기준:** 일상 작업은 `stu2603` 하나에서 수행하고 옛 채점 경로에 의존하지 않는다. 학생용 배포 URL과 라이브 시트 ID는 유지된다.

## 4. 복구 방법

전환 전에 문제가 생기면 통합 브랜치의 변경을 운영에 반영하지 않고 기존 저장소를 사용한다. 원본 디렉터리와 산출물을 보존하므로 파일 삭제를 통한 복구는 필요하지 않다.

전환 후 문제가 생기면 새 자동 실행을 먼저 중지하고 기존 작업 디렉터리와 실행 설정으로 복귀한다. 새 위치에 쌓인 산출물을 보존한 뒤 기존 환경에서 처리한다. Git revert는 코드만 되돌리며 시트 변경이나 발송된 이메일을 되돌리지 않는다. 새 학생 제출이나 기존 랩6 배정을 과거 스냅샷으로 일괄 덮어쓰지 않는다.

## 5. 최종 완료 기준

- [x] 하나의 비공개 저장소에서 수업 자료 작성부터 평가까지 처리한다.
- [x] 두 저장소의 Git 이력과 기존 로컬 산출물이 보존된다.
- [x] 공통 일정이 한 벌이고 공개·학생 안내·채점의 시각이 일치한다.
- [x] 기존 랩6 배정은 원래 해시와 내용을 유지한다.
- [x] 학생용 저장소 배포에 채점 데이터가 섞이지 않는다.
- [x] 채점 하네스·수정 주차 콘텐츠 검증이 통과하고 자동 실행이 중복되지 않는다.

## 6. 실행 진행 경과 (Execution Log)

### 2026-10-16 실행 기록

1. **작업1: 현재 상태 보존 및 백업 (완료)**
   - `eval-stu` 계획서 수정사항 커밋 완료: `2e06be9` (`docs: update repository unification plan with Git history and issue handling details`)
   - 사전 안전 태그 생성: 양쪽 저장소 모두 `pre-unification-20261016` 태그 생성
   - Git 번들 백업 생성:
     - `eval-stu/tmp/eval-stu-pre-unification.bundle` (HEAD)
     - `eval-stu/tmp/stu2603-pre-unification.bundle` (HEAD)
   - 랩6 배정 산출물 해시 검증 및 보존 확인:
     - `9output/week6_peer_review_assignments_15143.md`: `a7313db0b67cd6f59528334b7108b94bfda3eb9753ab5ee12c49682c03ae9a38`
     - `9output/week6_peer_review_assignments_15144.md`: `851672a4cce13036b71fe0baf00365593e5743a5e053b534c0bfad50c1771537`

2. **작업2: 이력 보존 서브트리 편입 (완료)**
   - `stu2603`에 통합 전용 브랜치 생성: `integration/eval-stu`
   - `git subtree add --prefix=eval ../eval-stu main` 실행으로 1,716개 오브젝트 및 커밋 히스토리 편입 완료 (커밋: `851210c`)
   - `eval/` 하위 중첩 `.git` 없음 확인

3. **작업3: 내부 참조 및 환경 정리 (완료)**
   - 내부 상대 심볼릭 링크 재설정 완료:
     - `eval/5input/students` -> `../../5input/students`
     - `eval/5input/py` -> `../../2python-output`
     - `eval/5input/web` -> `../../3web-output`
     - `eval/5input/deadline.csv` -> `../../1docs/deadline.csv`
     - `eval/1docs/sheets.md` -> `../../1docs/sheets.md`
     - `eval/1docs/scores.md` -> `../../1docs/scores.md`
     - `eval/1docs/assignment-micro.md` -> `../../1docs/assignment-micro.md`
     - `eval/1docs/email-rules.md` -> `../../4advices/email-rules.md`
     - `eval/1docs/2603-cqi*.md` -> `../../output/cqi/2603-cqi*.md`
   - 공통 문서 루트 일원화: `weekly-assignment-workflow.md`, `repository-unification-plan.md`를 루트 `1docs/`로 이동 및 `eval/1docs/` 심볼릭 링크 연결 완료 (커밋: `feaf758`)
   - Git Ignore 차단 검증 완료 (`git check-ignore -v`): `eval/output/`, `eval/9output/`, `eval/tmp/`, `eval/.venv/` 완벽 차단 확인
   - 가상환경 재생성 완료: `stu2603/eval/.venv` 생성 및 `requirements.txt`, `requirements-test.txt` 설치 완료
   - 랩6 배정 파일 `eval/9output/` 복사 및 원본 해시 100% 일치 확인

4. **작업4: 단일 규칙·스킬·검증 진입점 통합 (완료)**
   - 루트 `AGENTS.md`에 수업 운영 및 학생 평가 통합 아키텍처 반영
   - `eval/AGENTS.md`를 `../AGENTS.md` 심볼릭 링크로 연결하여 단일 SSOT 보장
   - `.agents/skills/`에 평가 전용 스킬 3종(`email-hw-grader`, `moodle-tsv-converter`, `tis-grade-input`) 통합 이식
   - `.husky/pre-commit` 허용 루트 폴더에 `eval` 및 `5input` 추가
   - `.bin/harness-check.sh`에 eval 서브시스템 검증 게이트 연동 완료
   - 루트 `README.md`에 디렉터리 구조 및 작업별 실행 진입점 가이드 추가
   - 커밋 완료: `d3f9556`

5. **작업6: 무간섭 검증 및 공개 도구 안전 검증 (완료)**
   - `stu2603/eval`에서 `./bin/harness-check.sh` 실행: Black, Flake8, Mypy, Pytest (368 passed) 전체 통과
   - 루트에서 `.bin/harness-check.sh` 실행: 글로벌 7개 검증 게이트 100% 통과
   - `scripts/sync_student_repos.py --dry-run` 실행: `eval/` 및 채점 산출물 격리 유지 검증 완료

6. **작업7: 기존 저장소 안내 및 단일화 완료 (완료)**
   - `eval-stu/README.md`에 단일 통합 저장소(`wonhyukc/stu2603`) 편입 완료 배너 및 단일 관리 안내 반영 완료 (커밋: `11ba6b7`)


