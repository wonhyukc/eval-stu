# AGENTS.md — eval(py-stu) 운영 지침

학생 평가(과제 수집·채점·성적 관리) 자동화 저장소입니다. 프로젝트 개요와 디렉터리 구조는 `README.md` 참고.

- 스킬: `.agents/skills/<name>/SKILL.md` (Claude Code에는 `.claude/skills` 심볼릭 링크로 연동)
- 워크플로우: `.agents/workflows/*.md` (Claude Code에는 `.claude/commands` 심볼릭 링크로 연동)

## 강의안 저장소(../stu2603)와의 경계

- 강의안·과제 SSOT는 별도 저장소 `../stu2603`입니다. 이 저장소에서는 **읽기만** 하고, 수정은 stu2603 쪽에서 합니다.
- 교차 참조는 심볼릭 링크로 연결: `1docs/assignment-micro.md`, `1docs/scores.md`, `5input/py`, `5input/web`
- 교차 링크는 **항상 상대경로**로 만듭니다(마운트 경로 변경에도 살아남도록). 깨진 링크는 pre-commit 훅이 차단합니다.

## 핵심 제약

- **자격증명 파일 접근 금지**: `secret.json`, `credentials.json`, `token.json`, `gwsServiceAccnt-mail.json`은 읽지도, 출력하지도, 커밋하지도 않습니다.
- **학생 개인정보 보호**: 성적 CSV/TSV, 학생 사진, 이메일 본문은 git에 추가하지 않습니다 (`output/`, `9output/`, `*.csv`, `*.tsv`는 gitignore 유지).
- **파이썬 코드 검증**: `.py` 수정 후에는 `./bin/harness-check.sh`(Black·Flake8·Mypy·Pytest)를 통과해야 하며, pre-commit 훅이 강제합니다.
- 출력 폴더는 두 곳입니다: `output/`(채점·점수 CSV), `9output/`(상호평가 배정 md, 등급 산출물). 코드가 각각 참조하므로 임의로 합치지 않습니다.
