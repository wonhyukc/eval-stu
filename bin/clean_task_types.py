#!/usr/bin/env python3
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import (
    get_sheet_service,
    load_course_config,
    get_target_sheet_title,
)


def clean_sheet(course):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_course_config(base_dir, course)
    if not config:
        print(f"❌ '{course}' 설정이 없습니다.")
        return

    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")

    service = get_sheet_service(base_dir)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)
    if not sheet_title:
        print(f"❌ '{course}' 시트를 찾을 수 없습니다.")
        return

    print(
        f"\n🚀 [{course.upper()} 과정] 구글 시트('{sheet_title}') E컬럼 데이터 분석 및 클렌징 시작..."
    )

    range_name = f"{sheet_title}!A:E"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )
    values = result.get("values", [])

    if len(values) < 2:
        print("데이터가 없습니다.")
        return

    updates = []

    for row_idx, row in enumerate(
        values[1:], start=2
    ):  # 1-based index, row 1 is header
        if len(row) > 4:
            original_val = str(row[4])
            clean_val = (
                original_val.strip()
                .replace("과제", "")
                .replace("assignment", "")
                .strip()
            )

            if clean_val.lower() == "lab5" or clean_val.lower() == "lab 5":
                clean_val = "5"

            # 비정상 데이터 식별 (날짜 포맷이나 의미 없는 문자열 등)
            if "/" in clean_val:
                print(
                    f"⚠️ [수동확인 요망] 행 {row_idx}: (학번: {row[1] if len(row) > 1 else '?'}) | 비정상 유형 값 발견: '{original_val}'"
                )

            # 구글 시트에 문자열(Text)로 강제 지정되도록 ' 접두어 추가
            target_val = f"'{clean_val}"

            updates.append(
                {"range": f"{sheet_title}!E{row_idx}", "values": [[target_val]]}
            )

    if updates:
        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        resp = (
            service.spreadsheets()
            .values()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )
        print(
            f"✅ [{course.upper()}] 과정 E컬럼 포맷팅 완료! (총 {resp.get('totalUpdatedCells')}개 셀 강제 문자열 변환 적용)"
        )
    else:
        print("업데이트할 데이터가 없습니다.")


if __name__ == "__main__":
    clean_sheet("py")
    clean_sheet("web")
