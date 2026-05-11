# 워크로드 아이덴티티 제휴 (Workload Identity Federation) 가이드

이 문서는 Google Cloud의 **워크로드 아이덴티티 제휴(Workload Identity Federation)**에 대한 개념, 장단점, 그리고 실제 적용 방법을 안내합니다.

---

## 1. 개요
워크로드 아이덴티티 제휴는 Google Cloud 외부(AWS, Azure, 사내 Active Directory, GitHub Actions 등)에서 실행되는 워크로드가 **서비스 계정 키(JSON 키) 없이** Google Cloud 리소스에 인증하고 액세스할 수 있게 해주는 기능입니다. 

기존에는 서비스 계정 키를 발급받아 외부 시스템에 저장해야 했으나, 이제는 외부 ID 공급업체(IdP)의 사용자 인증 정보(예: OIDC 토큰)를 Google Cloud의 단기 엑세스 토큰으로 교환하여 인증합니다.

---

## 2. 장점 및 단점

### 장점 (장려되는 이유)
- **보안성 향상**: 수명이 긴 서비스 계정 키를 다운로드하여 깃허브나 외부 서버에 저장할 필요가 없으므로 키 유출 위험이 원천 차단됩니다.
- **유지보수 부담 감소**: 서비스 계정 키를 주기적으로 교체(Key Rotation)하거나 관리할 필요가 없습니다.
- **세밀한 액세스 제어**: 속성 매핑(Attribute Mapping)을 통해 특정 GitHub 리포지토리나 특정 AWS 역할(Role)에서만 접근을 허용하는 등 세밀하게 IAM 접근 제어가 가능합니다.

### 단점 및 한계점
- **초기 구성의 복잡함**: 외부 IdP, 워크로드 아이덴티티 풀(Pool), 공급업체(Provider), IAM 서비스 계정 가장 권한(Impersonation), 속성 조건(Attribute Condition) 등 설정 과정이 길고 다소 복잡합니다.
- **디버깅의 어려움**: 연결이나 인증 토큰 교환 단계에서 오류가 발생할 경우, 에러 메시지가 포괄적(예: 403 Forbidden)이어서 매핑 실수인지 권한 부족인지 정확한 원인을 추적하기 까다롭습니다.
- **오설정으로 인한 보안 위협(Blast Radius)**: 속성 매핑 시 조건(Attribute Condition)을 엄격하게 주지 않으면 예기치 않은 다른 리포지토리나 외부 워크로드가 Google Cloud 리소스에 접근할 수 있게 되는, 일명 '혼동된 대리자 문제(Confused Deputy Problem)'가 발생할 여지가 있습니다.
- **외부 IdP 의존성**: 인증서(OIDC 메타데이터)가 만료되거나 외부 시스템의 사양 변경 시 즉각적으로 영향을 받습니다.

---

## 3. 실제 적용하는 방법 (Step-by-Step)

가장 흔히 사용되는 **GitHub Actions CI/CD 환경**에서 서비스 계정 키 없이 리소스 접근 권한을 획득하는 과정을 예매로 설명합니다.

### 1단계: Google Cloud 서비스 계정(Service Account) 생성
Google Cloud 특정 리소스에 권한을 가진 서비스 계정을 하나 만듭니다.
\`\`\`bash
gcloud iam service-accounts create my-cicd-sa \\
    --display-name="CI/CD Service Account"

gcloud projects add-iam-policy-binding [프로젝트_ID] \\
    --member="serviceAccount:my-cicd-sa@[프로젝트_ID].iam.gserviceaccount.com" \\
    --role="roles/storage.admin" # 필요한 구글 클라우드 역할
\`\`\`

### 2단계: 워크로드 아이덴티티 풀(Pool) 생성
외부 ID를 관리할 논리적 컨테이너입니다.
\`\`\`bash
gcloud iam workload-identity-pools create "my-github-pool" \\
  --project="[프로젝트_ID]" \\
  --location="global" \\
  --display-name="GitHub Actions Pool"
\`\`\`

### 3단계: 풀에 공급업체(Provider) 추가 및 OIDC 조건 매핑
GitHub를 ID 공급업체로 추가하고, GitHub의 클레임(Claim)을 매핑합니다. 
> [!IMPORTANT]
> \`--attribute-condition\`을 사용하여 여러분의 특정 GitHub 리포지토리(\`user/repo\`)에서만 접근할 수 있도록 제한하는 것이 보안 핵심입니다!

\`\`\`bash
gcloud iam workload-identity-pools providers create-oidc "my-github-provider" \\
  --project="[프로젝트_ID]" \\
  --location="global" \\
  --workload-identity-pool="my-github-pool" \\
  --display-name="My GitHub Provider" \\
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \\
  --attribute-condition="assertion.repository == 'my-github-username/my-repo'" \\
  --issuer-uri="https://token.actions.githubusercontent.com"
\`\`\`

### 4단계: 워크로드 ID가 서비스 계정을 가장(Impersonate)하도록 허용
특정 GitHub 리포지토리의 ID(주 구성원)가 클라우드의 **서비스 계정을 사용할 수 있도록** 권한을 묶어줍니다.
\`\`\`bash
gcloud iam service-accounts add-iam-policy-binding "my-cicd-sa@[프로젝트_ID].iam.gserviceaccount.com" \\
  --project="[프로젝트_ID]" \\
  --role="roles/iam.workloadIdentityUser" \\
  --member="principalSet://iam.googleapis.com/projects/[프로젝트_번호]/locations/global/workloadIdentityPools/my-github-pool/attribute.repository/my-github-username/my-repo"
\`\`\`
*(주의: `[프로젝트_번호]`는 알파벳 ID가 아닌 10~12자리의 순수 숫자로 된 프로젝트 고유 번호입니다.)*

> [!NOTE]
> **💡 프로젝트 번호 확인 방법**
> 1. **Google Cloud Console (웹환경)**: 상단 대시보드(Dashboard) 메뉴로 이동하여 '프로젝트 정보(Project Info)' 카드에 있는 `프로젝트 번호(Project Number)`를 확인합니다.
> 2. **CLI (명령어 환경)**: 터미널에서 다음 명령어를 실행하면 해당 프로젝트의 번호만 출력됩니다.
>    `gcloud projects describe [프로젝트_ID] --format="value(projectNumber)"`

### 5단계: GitHub 워크플로(.github/workflows/*.yml) 설정
JSON 키를 Github Secrets에 등록할 필요 없이, OIDC로 직접 워크로드 ID를 증명합니다.
\`\`\`yaml
name: Deploy to Google Cloud

on:
  push:
    branches: [ "main" ]

# OIDC 토큰 발급을 위한 핵심 권한 허용
permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - name: Checkout code
      uses: actions/checkout@v3

    # Google Cloud 안전 인증 수행 (Json Key 없음)
    - name: Authenticate to Google Cloud
      uses: google-github-actions/auth@v1
      with:
        workload_identity_provider: 'projects/[프로젝트_번호]/locations/global/workloadIdentityPools/my-github-pool/providers/my-github-provider'
        service_account: 'my-cicd-sa@[프로젝트_ID].iam.gserviceaccount.com'

    # 인증되었으므로 gcloud, kubectl 명령어 등 자유롭게 자원 제어 가능
    - name: Set up Cloud SDK
      uses: google-github-actions/setup-gcloud@v1
      
    - name: Test Authentication
      run: gcloud storage ls
\`\`\`

위 단계대로 구성하면 비밀키를 파일 형태나 Secrets에 저장할 필요 없이 안전하게 Google Cloud 서비스에 접근할 수 있게 됩니다.
