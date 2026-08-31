import subprocess
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


def check_and_update_submissions():
    res = subprocess.run(
        ["secret-tool", "lookup", "Title", "drive-api"], capture_output=True, text=True
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

    # 1. Check progess-02
    res_02 = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="progess-02!A4:O36")
        .execute()
    )
    rows_02 = res_02.get("values", [])

    updates_02 = []
    github_users_02 = []

    for idx, r in enumerate(rows_02[1:]):
        row_num = 5 + idx
        sid = r[0] if len(r) > 0 else ""
        kname = r[1] if len(r) > 1 else ""
        ename = r[2] if len(r) > 2 else ""
        current_attn = r[4] if len(r) > 4 else ""
        gh = r[5] if len(r) > 5 else ""
        email = r[6] if len(r) > 6 else ""
        city = r[8] if len(r) > 8 else ""
        gender = r[9] if len(r) > 9 else ""
        scores = r[12:] if len(r) > 12 else []

        has_activity = bool(
            gh.strip()
            or email.strip()
            or city.strip()
            or gender.strip()
            or any(s.strip() for s in scores)
        )
        new_attn = "1" if has_activity else "0"

        if gh.strip():
            github_users_02.append((row_num, sid, kname, ename, gh.strip()))

        if current_attn != new_attn:
            updates_02.append(
                {"range": f"progess-02!E{row_num}", "values": [[new_attn]]}
            )
            print(
                f"[progess-02] Row {row_num} ({sid} {ename}) 출석 상태 갱신: {current_attn} -> {new_attn}"
            )

    if updates_02:
        body = {"valueInputOption": "USER_ENTERED", "data": updates_02}
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        ).execute()
        print(f"✅ progess-02: {len(updates_02)}건의 출석 상태를 업데이트했습니다.")

    print(f"📊 progess-02 현재 GitHub 등록자 수: {len(github_users_02)}명")
    for u in github_users_02:
        print(f"   • Row {u[0]} | {u[1]} {u[3]}: {u[4]}")

    return github_users_02


if __name__ == "__main__":
    check_and_update_submissions()
