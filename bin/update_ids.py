import os
import sys
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import get_sheet_service

SPREADSHEET_ID = "1lUdHWhyNDTZl9n7s48jn3FCrH6gcbQvGt1nkLBbIM9o"
TARGET_GID = 102396122
SOURCE_GID = 1889091726


def get_sheet_title(service, gid):
    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get("sheets", "")
    for s in sheets:
        props = s.get("properties", {})
        if props.get("sheetId") == int(gid):
            return props.get("title")
    return None


def normalize_name(name):
    if not name:
        return ""
    return re.sub(r"\s+", "", name).lower()


def get_name_words(name):
    if not name:
        return set()
    # 단어(어절) 단위로 분리하여 소문자 셋으로 반환
    return set(w.lower() for w in name.split())


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    service = get_sheet_service(base_dir)

    target_title = get_sheet_title(service, TARGET_GID)
    source_title = get_sheet_title(service, SOURCE_GID)

    if not target_title or not source_title:
        print("시트를 찾을 수 없습니다.")
        return

    # 1. 원본 시트 데이터 가져오기
    source_res = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"{source_title}!A2:H")
        .execute()
    )
    source_rows = source_res.get("values", [])

    source_students = []
    for row in source_rows:
        if len(row) > 4:
            korean_name = row[2] if len(row) > 2 else ""
            student_id = row[4]
            english_name = row[5] if len(row) > 5 else ""

            if student_id:
                source_students.append(
                    {
                        "id": student_id,
                        "kor_norm": normalize_name(korean_name),
                        "eng_norm": normalize_name(english_name),
                        "eng_words": get_name_words(english_name),
                        "original_eng": english_name,
                    }
                )

    # 2. 타겟 시트 데이터 가져오기
    target_res = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"{target_title}!A2:F")
        .execute()
    )
    target_rows = target_res.get("values", [])

    updates = []

    for i, row in enumerate(target_rows):
        student_id = row[0] if len(row) > 0 else ""
        name = row[4] if len(row) > 4 else ""

        # 학번이 비어있거나 숫자가 아닌 경우
        if not student_id or not student_id.isdigit():
            norm_name = normalize_name(name)
            name_words = get_name_words(name)
            found_id = None

            # 먼저 완전 일치 검사
            for stu in source_students:
                if stu["kor_norm"] == norm_name or stu["eng_norm"] == norm_name:
                    found_id = stu["id"]
                    break

            # 완전 일치가 없으면, 단어 교집합(부분 일치) 검사
            if not found_id and name_words:
                best_match = None
                best_score = 0
                for stu in source_students:
                    if stu["eng_words"]:
                        intersect = name_words.intersection(stu["eng_words"])
                        if len(intersect) > best_score:
                            best_score = len(intersect)
                            best_match = stu["id"]

                # 최소 2개의 단어가 겹치거나, 아예 1단어 이름인데 그것이 일치하는 경우 등 휴리스틱
                if best_score > 0 and (
                    best_score >= len(name_words) - 1
                    or best_score >= len(stu["eng_words"]) - 1
                ):
                    found_id = best_match

            if found_id:
                print(f"Row {i+2}: 찾음 -> '{name}' : 학번 {found_id}")
                cell_range = f"{target_title}!A{i+2}"
                updates.append({"range": cell_range, "values": [[found_id]]})
            else:
                print(f"Row {i+2}: 실패 -> '{name}'에 대한 학번을 찾을 수 없음")

    print(f"\n총 업데이트할 레코드 수: {len(updates)}")

    # 3. 데이터 업데이트 반영
    if updates:
        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        result = (
            service.spreadsheets()
            .values()
            .batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body)
            .execute()
        )
        print(
            f"업데이트 완료: {result.get('totalUpdatedCells')} 개의 셀이 갱신되었습니다."
        )
    else:
        print("업데이트할 항목이 없습니다.")


if __name__ == "__main__":
    main()
