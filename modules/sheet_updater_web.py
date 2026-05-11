import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# 1prd.md에 선언된 타겟 시트 ID 및 gid (웹 과제 시트)
SPREADSHEET_ID = "1XA5Hnu5PEidFMreanPCy1eMrofGiyFDPo4buN3129Mc"
TARGET_GID = 1514293361


import google.auth


def get_sheet_service():
    # 프로젝트 최상단 폴더의 secret.json 위치 계산
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def get_target_sheet_title(service):
    """
    메타데이터를 조회하여 TARGET_GID와 일치하는 시트(탭)의 실제 이름을 가져옵니다.
    """
    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get("sheets", "")
    for s in sheets:
        props = s.get("properties", {})
        if props.get("sheetId") == TARGET_GID:
            return props.get("title")
    return None


def get_max_no(service, sheet_title):
    """A열을 읽어 기존 일련번호(no) 중 최대값을 반환합니다."""
    range_name = f"{sheet_title}!A:A"
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=range_name)
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


def append_grades_to_sheet(rows_data):
    """
    파싱된 CSV 형태의 리스트(rows_data)를 타겟 시트의 맨 아래(빈 행)에 추가(Append)합니다.
    rows_data 구조 예시: [['', '학번', '트랙', '점수', '유형', '이유', '날짜', '이름', '제목'], ...]
    """
    service = get_sheet_service()
    sheet_title = get_target_sheet_title(service)

    if not sheet_title:
        print(f"❌ 오류: 시트 ID(gid={TARGET_GID})를 찾을 수 없습니다.")
        return False

    # 기존 데이터에서 최대 no 조회 후 새로 추가될 데이터에 순차적으로 no 할당
    max_no = get_max_no(service, sheet_title)
    for i, row in enumerate(rows_data):
        row[0] = max_no + i + 1

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
                spreadsheetId=SPREADSHEET_ID,
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
