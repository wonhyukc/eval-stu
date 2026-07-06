# py-stu (학생 평가 관리 시스템)

학생들의 성적과 과제 제출 내역을 자동으로 수집(Gmail)하고, 채점 결과를 구글 시트(Google Sheets)에 연동하여 관리하는 Python 백엔드 자동화 프로젝트입니다.

## 🎯 주요 기능
- **이메일 자동 수집 및 채점**: 수신된 이메일의 제목 키워드(`과제`, `assignment`)를 파싱하여 학번을 식별하고, 제출 시간에 따라 자동으로 채점(CSV 추출)
- **구글 시트 연동**: 채점된 대상 데이터(예: `score1.csv`)를 학생별/과목별 구글 스프레드시트에 자동으로 Append(추가) 기록
- **안전한 인증 관리**: `secret.json` 등 인증 파일을 활용한 백그라운드 봇 환경 구축

---

## 📂 주요 디렉터리 및 데이터

- `5input/students/`: 대상 과목 및 학생, 시간표 메타데이터
  - `py-students.md`: 파이썬 분반 목록
  - `wb-students.md`: 웹 프로그래밍 2개 분반 목록
  - `timetable.md`: 전체 시간표
- `5input/py`, `5input/web`: 강의안 저장소(`../stu2603`)의 주차별 산출물로 향하는 심볼릭 링크 (읽기 전용, 항상 상대경로 유지)
- `1docs/`: 채점 정책·운영 매뉴얼 문서 (`assignment-micro.md`, `scores.md`는 `../stu2603`으로의 심볼릭 링크)
- `modules/`: 기능별(구글 시트, 이메일 파싱 등) 독립 모듈 (라이브러리 성격)
- `bin/`: 하네스 검증 스크립트(`harness-check.sh`)와 채점·성적 처리 실행 스크립트(`fetch_gmail.py`, `calculate_final_grades.py` 등)
- `scripts/`: 일회성 변환·실험 스크립트 (`scripts/test_*.py`는 pytest 테스트가 아닌 실험용 스크립트)
- `tests/`: pytest 단위 테스트
- `output/`: 채점·점수 CSV 출력 / `9output/`: 상호평가 배정 md, 등급 산출물 (둘 다 git 미추적)

---

## 🔐 인증 및 자격 증명 (Credentials)

프로젝트 내 Google API 통합을 위해 환경에 따라 다음과 같은 인증 파일이 요구될 수 있습니다. (주로 `secret.json` 사용)

| 파일명 | 용도 및 설명 |
|---|---|
| **`secret.json`** | **(메인)** 사용자의 개입 없는 백그라운드 환경용 서비스 계정 개인키입니다. 타겟 스프레드시트에 편집자 권한으로 계정 이메일을 공유해야 쓰기가 가능합니다. |
| **`credentials.json`** | 관리자(교강사) 계정으로 인증 절차를 밟기 위한 OAuth 2.0 클라이언트 ID 파일입니다. |
| **`token.json`** | `credentials.json` 최초 인증 후 발급받아 재사용하는 권한 갱신용 접속 토큰 파일입니다. |

> ⚠️ **보안 주의**: 모든 인증 JSON 파일은 절대 Git 저장소에 포함되지 않도록 `.gitignore`에 등록하여 관리해야 하며, AI 에이전트의 접근도 엄격히 제한됩니다.

---

## ⚙️ 개발 및 환경 설정 (Getting Started)

프로젝트를 로컬에 세팅하고 코드를 변경하려면 반드시 아래의 절차를 통해 하네스(Harness) 검증 환경을 갖춰야 합니다.

### 1. 가상환경 구성
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. 의존성 패키지 설치
```bash
pip install -r requirements-test.txt
```

### 3. 하네스(Harness) 무결성 체크
코드나 스크립트를 수정한 후에는 코드를 실행하기 전 반드시 내장된 스크립트를 통해 문법 오류 여부를 검증해야 합니다. (SSOT 기준 원칙 적용)
```bash
bin/harness-check.sh
```

---

## 🛠 Google API 환경 세팅 가이드 (서비스 계정 발급)

1. **[Google Cloud Console](https://console.cloud.google.com/)** 접속 및 구글 클라우드 프로젝트 생성
2. `API 및 서비스` > `라이브러리`에서 **Google Sheets API** 및 **Gmail API** (필요시) 사용 설정
3. `사용자 인증 정보` 메뉴에서 **서비스 계정(Service Account)** 생성
4. 계정 상세 탭에서 **새 키(JSON)**를 생성 및 다운로드 후 파일명을 `secret.json`으로 변경하여 프로젝트 루트에 저장
5. 스프레드시트 우측 상단 '공유' 버튼을 눌러, 생성한 서비스 계정 메일 주소(예: `@...iam.gserviceaccount.com`)를 **[편집자]** 권한으로 추가
6. _(선택: 학교/기관 계정 메일 제어 시)_ Google Workspace 관리자 콘솔에서 해당 클라이언트 ID에 대해 **도메인 전체 위임(Domain-Wide Delegation)** 부여 필수