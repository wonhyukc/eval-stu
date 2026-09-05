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
        print(
            "ℹ️ secret.json이 없으므로 WIF(Application Default Credentials)를 시도합니다."
        )
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
        print(
            f"❌ 오류: '{course}' 과정의 sheet_id 또는 target_gid가 올바르지 않습니다."
        )
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
        # '유형(Type)' 컬럼(인덱스 4)에 대해, 구글 시트가 숫자로 자동 변환하지 못하도록 문자열 강제 포맷팅(') 적용
        if len(row) > 4:
            clean_type = str(row[4]).replace("과제", "").replace("'", "").strip()
            row[4] = f"'{clean_type}"
        # '메일제목(Subject)' 컬럼(인덱스 8)에 대해, 순수 숫자가 숫자로 자동 변환되지 않도록 문자열 강제 포맷팅(') 적용
        if len(row) > 8:
            clean_subject = str(row[8]).lstrip("'")
            row[8] = f"'{clean_subject}"

    range_name = f"{sheet_title}!A:I"  # A~I열까지 데이터 기준으로 append
    body = {"values": rows_data}

    print(
        f"📝 구글 시트 '{sheet_title}' 탭에 {len(rows_data)}개의 데이터 추가를 시도합니다..."
    )

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
        print(
            f"✅ 구글 시트 업데이트 완료: 성공적으로 {updated_rows}개 행이 추가되었습니다!"
        )
        return True

    except Exception as e:
        print(f"❌ 구글 시트 업데이트 실패: {e}")
        return False


def upsert_grades_to_sheet(rows_data, course="py"):
    """
    (StudentID, Type) 복합 키를 기준으로 멱등성(Idempotency)을 보장하는 Upsert 함수.
    - 기존 행에 동일한 (학번, 과제유형)이 존재하면 해당 행을 갱신(Update).
    - 존재하지 않으면 최하단에 신규 추가(Append).
    - 스크립트를 N번 실행해도 중복 데이터가 누적되지 않음.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_course_config(base_dir, course)

    if not config:
        print(f"❌ 오류: settings.json에 '{course}' 과정에 대한 설정이 없습니다.")
        return False

    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")

    if not spreadsheet_id or target_gid is None:
        print(
            f"❌ 오류: '{course}' 과정의 sheet_id 또는 target_gid가 올바르지 않습니다."
        )
        return False

    service = get_sheet_service(base_dir)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)

    if not sheet_title:
        print(f"❌ 오류: 시트 ID(gid={target_gid})를 찾을 수 없습니다.")
        return False

    # 기존 시트의 전체 데이터 읽기 (2행부터)
    range_all = f"{sheet_title}!A2:I"
    try:
        res = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_all)
            .execute()
        )
        existing_rows = res.get("values", [])
    except Exception as e:
        print(f"⚠️ 기존 데이터 조회 실패: {e}")
        existing_rows = []

    # 기존 데이터 인덱싱: (student_id, clean_type) -> row_index (1-based from A2, so row_number = idx + 2)
    key_to_row_num = {}
    for idx, row in enumerate(existing_rows):
        if len(row) > 4:
            sid = str(row[1]).strip()
            ctype = str(row[4]).replace("과제", "").replace("'", "").strip()
            key_to_row_num[(sid, ctype)] = idx + 2

    # 새 데이터 포맷팅 및 업데이트 / 신규 추가 분류
    rows_to_update = []  # (row_number, formatted_row)
    rows_to_append = []

    max_no = get_max_no(service, spreadsheet_id, sheet_title)

    for row in rows_data:
        if len(row) > 4:
            clean_type = str(row[4]).replace("과제", "").replace("'", "").strip()
            row[4] = f"'{clean_type}"
        # '메일제목(Subject)' 컬럼(인덱스 8)에 대해, 순수 숫자가 숫자로 자동 변환되지 않도록 문자열 강제 포맷팅(') 적용
        if len(row) > 8:
            clean_subject = str(row[8]).lstrip("'")
            row[8] = f"'{clean_subject}"

        if len(row) > 4:
            sid = str(row[1]).strip()
            key = (sid, clean_type)

            if key in key_to_row_num:
                # 기존 행 갱신 (No는 기존 행의 No 유지)
                existing_row_num = key_to_row_num[key]
                existing_row_idx = existing_row_num - 2
                existing_no = (
                    existing_rows[existing_row_idx][0]
                    if len(existing_rows[existing_row_idx]) > 0
                    else row[0]
                )
                row[0] = existing_no
                rows_to_update.append((existing_row_num, row))
            else:
                # 신규 추가
                max_no += 1
                row[0] = max_no
                rows_to_append.append(row)
        else:
            rows_to_append.append(row)

    success = True

    # 1. 기존 행 멱등 갱신 (Update)
    for row_num, row in rows_to_update:
        try:
            update_range = f"{sheet_title}!A{row_num}:I{row_num}"
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            ).execute()
        except Exception as e:
            print(f"⚠️ 행 {row_num} 갱신 실패: {e}")
            success = False

    if rows_to_update:
        print(f"🔄 멱등 갱신 완료: {len(rows_to_update)}개 기존 행 업데이트됨")

    # 2. 신규 행 추가 (Append)
    if rows_to_append:
        try:
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_title}!A:I",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows_to_append},
            ).execute()
            print(f"➕ 신규 추가 완료: {len(rows_to_append)}개 신규 행 추가됨")
        except Exception as e:
            print(f"❌ 신규 행 추가 실패: {e}")
            success = False

    return success
