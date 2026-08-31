import subprocess
import json
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


def extract_gh_id(raw):
    if not raw:
        return ""
    raw = str(raw).strip()
    m = re.search(r"github\.com/([a-zA-Z0-9_\-\.]+)", raw)
    if m:
        return m.group(1).rstrip("/")
    if " " not in raw and not raw.startswith("http") and "@" not in raw:
        return raw.strip("/")
    return ""


def check_and_update_submissions():
    res = subprocess.run(
        ["secret-tool", "lookup", "Title", "drive-api"],
        capture_output=True,
        text=True,
    )
    if not res.stdout.strip():
        print("Failed to get credentials from keyring")
        return []

    data = json.loads(res.stdout.strip())
    creds = Credentials.from_service_account_info(
        data, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    spreadsheet_id = "1OMeWuYt45TZMygmkh5hOhqSCCUFYJv4iE0hTY554iAo"

    all_github_users = []

    # Check progess-01
    res_01 = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="progess-01!A4:AZ35")
        .execute()
    )
    rows_01 = res_01.get("values", [])
    for idx, r in enumerate(rows_01[1:]):
        row_num = 5 + idx
        sid = r[2] if len(r) > 2 else ""
        kname = r[3] if len(r) > 3 else ""
        ename = r[4] if len(r) > 4 else ""
        raw_gh = r[6] if len(r) > 6 else ""
        gh = extract_gh_id(raw_gh)
        if gh:
            all_github_users.append(("01반", row_num, sid, kname, ename, gh, raw_gh))

    # Check progess-02
    res_02 = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="progess-02!A4:AZ36")
        .execute()
    )
    rows_02 = res_02.get("values", [])
    for idx, r in enumerate(rows_02[1:]):
        row_num = 5 + idx
        sid = r[0] if len(r) > 0 else ""
        kname = r[1] if len(r) > 1 else ""
        ename = r[2] if len(r) > 2 else ""
        raw_gh = r[5] if len(r) > 5 else ""
        gh = extract_gh_id(raw_gh)
        if gh:
            all_github_users.append(("02반", row_num, sid, kname, ename, gh, raw_gh))

    print(f"📊 전체 (01반 + 02반) GitHub 등록자 수: {len(all_github_users)}명")
    return all_github_users


if __name__ == "__main__":
    check_and_update_submissions()
