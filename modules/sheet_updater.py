import os
import json
import re

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    import google.auth
except ImportError:
    Credentials = None
    build = None
    google = None

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def load_course_config(base_dir, course="py"):
    settings_file = os.path.join(base_dir, "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return settings.get("courses", {}).get(course)
    return None


def get_sheet_service(base_dir):
    # 크레덴셜 후보 경로 순서대로 탐색
    candidates = [
        os.path.join(base_dir, "secret.json"),
        os.path.expanduser("~/nvme_data/prj/exchange/service-account.json"),
    ]
    secret_path = next((p for p in candidates if os.path.exists(p)), None)

    if secret_path:
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    else:
        try:
            import subprocess

            res = subprocess.run(
                ["secret-tool", "lookup", "Title", "drive-api"],
                capture_output=True,
                text=True,
            )
            if res.stdout.strip():
                data = json.loads(res.stdout.strip())
                creds = Credentials.from_service_account_info(data, scopes=SCOPES)
            else:
                print(
                    "ℹ️ 서비스 계정 키 파일이 없으므로 Application Default Credentials를 시도합니다."
                )
                creds, _ = google.auth.default(scopes=SCOPES)
        except Exception:
            print(
                "ℹ️ 서비스 계정 키 파일이 없으므로 Application Default Credentials를 시도합니다."
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


def normalize_row_to_11cols(row):
    """
    행 데이터를 표준 11열 구조로 정규화합니다.
    [No, wk, ID, Track, Score, Type1, Type2, Reason, Date, Name, Subject] (A~K)
    구 9열 구조([No, StudentID, Track, Score, Type, Reason, Date, Name, Subject])가 들어오면
    11열 구조로 자동 확장 변환합니다.
    """
    if len(row) == 9:
        no, sid, track, score, ctype, reason, dt, name, subj = row
        clean_t = str(ctype).replace("과제", "").replace("'", "").strip()
        m = re.search(r"0\.(\d+)", clean_t)
        wk = m.group(1) if m else ""
        return [no, wk, sid, track, score, "hw", ctype, reason, dt, name, subj]
    elif len(row) < 11:
        extended = list(row) + [""] * (11 - len(row))
        return extended
    return list(row)


def route_web_rows(rows_data):
    """
    web 강좌의 행 데이터에서 Track 컬럼을 분석하여
    1반(web1)과 2반(web2)으로 자동 분류합니다.
    11열 구조: Track은 인덱스 3 (D열)
    구 9열 구조: Track은 인덱스 2 (C열)
    """
    web1_tracks = {"15143", "01", "761", "web1", "웹1"}
    web1_rows = []
    web2_rows = []

    for row in rows_data:
        track_idx = 3 if len(row) > 9 else 2
        track = str(row[track_idx]).strip() if len(row) > track_idx else ""
        if track in web1_tracks:
            web1_rows.append(row)
        else:
            web2_rows.append(row)

    return web1_rows, web2_rows


def append_grades_to_sheet(rows_data, course="py"):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # course가 "web"으로 지정된 경우, 1반(web1)과 2반(web2)으로 자동 분기하여 각각의 시트에 기록
    if course == "web":
        web1_rows, web2_rows = route_web_rows(rows_data)
        success = True
        if web1_rows:
            print(
                f"📦 [웹 1반(web1)] {len(web1_rows)}개 행을 1반 시트로 분기 추가합니다."
            )
            if not append_grades_to_sheet(web1_rows, course="web1"):
                success = False
        if web2_rows:
            print(
                f"📦 [웹 2반(web2)] {len(web2_rows)}개 행을 2반 시트로 분기 추가합니다."
            )
            if not append_grades_to_sheet(web2_rows, course="web2"):
                success = False
        return success

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
    normalized_rows = [normalize_row_to_11cols(r) for r in rows_data]

    for i, row in enumerate(normalized_rows):
        row[0] = max_no + i + 1
        # '학번(ID)' 컬럼(인덱스 2)에 대해, 지수 표기 방지를 위해 문자열 강제 포맷팅(') 적용
        if len(row) > 2 and row[2]:
            clean_id = str(row[2]).lstrip("'")
            row[2] = f"'{clean_id}"
        # 'Type2' 컬럼(인덱스 6)에 대해, 구글 시트가 숫자로 자동 변환하지 못하도록 문자열 강제 포맷팅(') 적용
        if len(row) > 6 and row[6]:
            clean_type2 = str(row[6]).replace("과제", "").replace("'", "").strip()
            row[6] = f"'{clean_type2}"
        # '메일제목(Subject)' 컬럼(인덱스 10)에 대해, 순수 숫자가 숫자로 자동 변환되지 않도록 문자열 강제 포맷팅(') 적용
        if len(row) > 10 and row[10]:
            clean_subject = str(row[10]).lstrip("'")
            row[10] = f"'{clean_subject}"

    range_name = f"{sheet_title}!A:K"  # A~K열 11열 데이터 기준으로 append
    body = {"values": normalized_rows}

    print(
        f"📝 구글 시트 '{sheet_title}' 탭에 {len(normalized_rows)}개의 데이터 추가를 시도합니다..."
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
    (StudentID, Type1, Type2) 복합 키를 기준으로 멱등성(Idempotency)을 보장하는 Upsert 함수.
    - 기존 행에 동일한 (학번, 대분류, 세부유형)이 존재하면 해당 행을 갱신(Update).
    - 존재하지 않으면 최하단에 신규 추가(Append).
    - 스크립트를 N번 실행해도 중복 데이터가 누적되지 않음.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # course가 "web"으로 지정된 경우, 1반(web1)과 2반(web2)으로 자동 분기하여 각각 멱등 동기화
    if course == "web":
        web1_rows, web2_rows = route_web_rows(rows_data)
        success = True
        if web1_rows:
            print(
                f"📦 [웹 1반(web1)] {len(web1_rows)}개 행을 1반 시트로 멱등 동기화합니다."
            )
            if not upsert_grades_to_sheet(web1_rows, course="web1"):
                success = False
        if web2_rows:
            print(
                f"📦 [웹 2반(web2)] {len(web2_rows)}개 행을 2반 시트로 멱등 동기화합니다."
            )
            if not upsert_grades_to_sheet(web2_rows, course="web2"):
                success = False
        return success

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

    # 기존 시트의 전체 데이터 읽기 (2행부터 A~K)
    range_all = f"{sheet_title}!A2:K"
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

    # 기존 데이터 인덱싱: (student_id, type1, type2) -> row_number (idx + 2)
    key_to_row_num = {}
    for idx, row in enumerate(existing_rows):
        if len(row) > 6:  # 11열 기준: ID=2, Type1=5, Type2=6
            sid = str(row[2]).replace("'", "").strip()
            t1 = str(row[5]).strip()
            t2 = str(row[6]).replace("과제", "").replace("'", "").strip()
            key_to_row_num[(sid, t1, t2)] = idx + 2
        elif len(row) > 4:  # 구 9열 기준 호환: ID=1, Type=4
            sid = str(row[1]).replace("'", "").strip()
            t1 = "hw"
            t2 = str(row[4]).replace("과제", "").replace("'", "").strip()
            key_to_row_num[(sid, t1, t2)] = idx + 2

    # 새 데이터 포맷팅 및 업데이트 / 신규 추가 분류
    rows_to_update = []  # (row_number, formatted_row)
    rows_to_append = []

    max_no = get_max_no(service, spreadsheet_id, sheet_title)
    normalized_rows = [normalize_row_to_11cols(r) for r in rows_data]

    for row in normalized_rows:
        # ID 포맷팅 (인덱스 2)
        if len(row) > 2 and row[2]:
            clean_id = str(row[2]).replace("'", "").strip()
            row[2] = f"'{clean_id}"
        else:
            clean_id = ""

        # Type1
        t1 = str(row[5]).strip() if len(row) > 5 else "hw"
        row[5] = t1

        # Type2 포맷팅 (인덱스 6)
        if len(row) > 6 and row[6]:
            clean_type2 = str(row[6]).replace("과제", "").replace("'", "").strip()
            row[6] = f"'{clean_type2}"
        else:
            clean_type2 = ""

        # Subject 포맷팅 (인덱스 10)
        if len(row) > 10 and row[10]:
            clean_subject = str(row[10]).lstrip("'")
            row[10] = f"'{clean_subject}"

        key = (clean_id, t1, clean_type2)

        if key in key_to_row_num:
            # 기존 행 갱신 (No는 기존 행의 No 유지)
            existing_row_num = key_to_row_num[key]
            existing_row_idx = existing_row_num - 2
            existing_no = (
                existing_rows[existing_row_idx][0]
                if (
                    existing_row_idx < len(existing_rows)
                    and len(existing_rows[existing_row_idx]) > 0
                )
                else row[0]
            )
            row[0] = existing_no
            rows_to_update.append((existing_row_num, row))
        else:
            # 신규 추가
            max_no += 1
            row[0] = max_no
            rows_to_append.append(row)

    success = True

    # 1. 기존 행 멱등 갱신 (Update)
    for row_num, row in rows_to_update:
        try:
            update_range = f"{sheet_title}!A{row_num}:K{row_num}"
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
                range=f"{sheet_title}!A:K",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows_to_append},
            ).execute()
            print(f"➕ 신규 추가 완료: {len(rows_to_append)}개 신규 행 추가됨")
        except Exception as e:
            print(f"❌ 신규 행 추가 실패: {e}")
            success = False

    return success
