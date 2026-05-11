import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

import google.auth

def load_course_config(base_dir, course="py"):
    settings_file = os.path.join(base_dir, "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return settings.get("courses", {}).get(course)
    return None

def get_sheet_service(base_dir):
    secret_path = os.path.join(base_dir, "secret.json")

    if os.path.exists(secret_path):
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    else:
        print("ℹ️ secret.json이 없으므로 WIF(Application Default Credentials)를 시도합니다.")
        creds, _ = google.auth.default(scopes=SCOPES)

    # cache_discovery=False 로 무한 지연 에러 원천 차단
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_target_sheet_title(service, spreadsheet_id, target_gid):
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = sheet_metadata.get("sheets", "")
    for s in sheets:
        props = s.get("properties", {})
        if props.get("sheetId") == target_gid:
            return props.get("title")
    return None


def get_max_no(service, spreadsheet_id, sheet_title):
    range_name = f"{sheet_title}!A:A"
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        max_no = 0
        for row in values:
            if row and str(row[0]).isdigit():
                max_no = max(max_no, int(row[0]))
        return max_no
    except Exception as e:
        print(f"⚠️ 일련번호(no) 조회 실패. 기본값 0 사용: {e}")
        return 0


def append_grades_to_sheet(rows_data, course="py"):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_course_config(base_dir, course)
    
    if not config:
        print(f"❌ 오류: settings.json에 '{course}' 과정에 대한 설정이 없습니다.")
        return False
        
    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")

    if not spreadsheet_id or target_gid is None:
        print(f"❌ 오류: '{course}' 과정의 sheet_id 또는 target_gid가 올바르지 않습니다.")
        return False

    service = get_sheet_service(base_dir)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)

    if not sheet_title:
        print(f"❌ 오류: 시트 ID(gid={target_gid})를 찾을 수 없습니다.")
        return False

    # 기존 데이터에서 최대 no 조회 후 새로 추가될 데이터에 순차적으로 no 할당
    max_no = get_max_no(service, spreadsheet_id, sheet_title)
    for i, row in enumerate(rows_data):
        row[0] = max_no + i + 1

    range_name = f"{sheet_title}!A:I"  # A~I열까지 데이터 기준으로 append
    body = {"values": rows_data}

    print(f"📝 구글 시트 '{sheet_title}' 탭에 {len(rows_data)}개의 데이터 추가를 시도합니다...")

    try:
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

        updates = result.get("updates", {})
        updated_rows = updates.get("updatedRows", 0)
        print(f"✅ 구글 시트 업데이트 완료: 성공적으로 {updated_rows}개 행이 추가되었습니다!")
        return True

    except Exception as e:
        print(f"❌ 구글 시트 업데이트 실패: {e}")
        return False
