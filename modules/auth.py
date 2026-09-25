import json
import os
import os.path
import subprocess

from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
USER_EMAIL = "wonhyukc@stu.ac.kr"


def _resolve_service_account_creds():
    """
    sheet_updater.py와 동일한 우선순위로 서비스 계정을 탐색합니다:
      1) 프로젝트 루트의 secret.json
      2) ~/nvme_data/prj/exchange/service-account.json
      3) secret-tool lookup Title drive-api (KeePass/Keyring)
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, "secret.json"),
        os.path.expanduser("~/nvme_data/prj/exchange/service-account.json"),
    ]
    secret_path = next((p for p in candidates if os.path.exists(p)), None)

    if secret_path:
        return SACredentials.from_service_account_file(secret_path, scopes=SCOPES)

    # secret-tool (KeePass/Keyring) 폴백
    try:
        res = subprocess.run(
            ["secret-tool", "lookup", "Title", "drive-api"],
            capture_output=True,
            text=True,
        )
        if res.stdout.strip():
            data = json.loads(res.stdout.strip())
            return SACredentials.from_service_account_info(data, scopes=SCOPES)
    except Exception:
        pass

    return None


def get_gmail_service(credentials_file="credentials.json", token_file="token.json"):
    """
    Gmail API(읽기 전용) 서비스 객체를 반환합니다.

    인증 우선순위:
      1) 서비스 계정 + DWD (sheet_updater.py와 동일 경로)
      2) 기존 OAuth token.json
      3) OAuth credentials.json → 브라우저 인증 흐름
    """
    # ── 1) 서비스 계정 + Domain-Wide Delegation ──
    sa_creds = _resolve_service_account_creds()
    if sa_creds:
        delegated = sa_creds.with_subject(USER_EMAIL)
        try:
            service = build("gmail", "v1", credentials=delegated, cache_discovery=False)
            # 연결 테스트 (DWD 미설정이면 여기서 예외)
            service.users().getProfile(userId="me").execute()
            return service
        except Exception as e:
            print(f"⚠️ 서비스 계정 DWD 실패 (OAuth 폴백): {e}")

    # ── 2) 기존 OAuth token.json ──
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if creds and creds.valid:
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ── 3) OAuth 브라우저 인증 흐름 ──
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif os.path.exists(credentials_file):
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)
    else:
        raise RuntimeError(
            "❌ Gmail 인증 수단 없음: "
            "서비스 계정(DWD), token.json, credentials.json 모두 없습니다.\n"
            "  → drive-project-84200 콘솔에서 OAuth 클라이언트(데스크톱)를 만들고\n"
            "    credentials.json을 프로젝트 루트에 저장하세요."
        )

    with open(token_file, "w") as token:
        token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


if __name__ == "__main__":
    print("Gmail API 인증 모듈 테스트 중...")
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"인증 성공! 이메일 계정: {profile['emailAddress']}")
