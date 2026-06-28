#!/usr/bin/env python3
import sys
import os
import argparse
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import google.auth

# 사용자가 지정한 통합 성적 시트 ID
SPREADSHEET_ID = "1lUdHWhyNDTZl9n7s48jn3FCrH6gcbQvGt1nkLBbIM9o"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheet_service(base_dir):
    secret_path = os.path.join(base_dir, "secret.json")
    if os.path.exists(secret_path):
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    else:
        creds, _ = google.auth.default(scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_sheet_data(service, spreadsheet_id, sheet_title):
    """지정된 시트 탭의 전체 데이터를 읽어와 (헤더, 행목록) 형태로 반환합니다."""
    range_name = f"'{sheet_title}'!A:Z"
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            return [], []
        return values[0], values[1:]
    except Exception as e:
        print(f"⚠️ 탭 '{sheet_title}' 읽기 실패 (탭이 존재하지 않을 수 있습니다): {e}")
        return [], []


def extract_score(row, header):
    """
    row에서 점수(숫자)를 추출하는 헬퍼 함수.
    '점수', 'score', '총점', '최종점수' 등이 포함된 열이나,
    그게 없다면 숫자로 변환 가능한 첫 번째 열의 값을 반환합니다.
    """
    if not row or not header:
        return 0.0

    score_idx = -1
    for i, h in enumerate(header):
        h_str = str(h).lower()
        if any(
            keyword in h_str
            for keyword in ["점수", "score", "총점", "합계", "최종", "기말"]
        ):
            score_idx = i
            break

    if score_idx != -1 and len(row) > score_idx:
        val = row[score_idx]
        try:
            return float(str(val).replace(",", "").strip())
        except ValueError:
            pass

    # 명시적인 키워드가 없다면 뒤에서부터 첫번째로 파싱되는 숫자를 찾습니다.
    for val in reversed(row):
        try:
            return float(str(val).replace(",", "").strip())
        except ValueError:
            continue

    return 0.0


def find_id_index(header):
    for i, h in enumerate(header):
        h_str = str(h).replace(" ", "").lower()
        if "학번" in h_str or "studentid" in h_str or "id" == h_str:
            return i
    return -1


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    service = get_sheet_service(base_dir)

    print("🚀 [최종 성적 통합 산출 시작]")

    # 1. 학생 기본 명단 및 분반 정보 수집
    students = (
        {}
    )  # { student_id: {"name": "", "track": "", "기말": 0, "중간": 0, "과제_이메일": 0, "과제_상호평가": 0, "수업태도": 0} }

    # 각 분반(468, 761, 762) 탭에서 학생 정보 및 기말고사 점수를 수집합니다.
    # 사용자가 분반 탭에 기말고사 채점을 했다고 했으므로, 이 탭들을 베이스로 씁니다.
    for track in ["468", "761", "762"]:
        header, rows = read_sheet_data(service, SPREADSHEET_ID, track)
        if not rows:
            print(f"⚠️ {track} 탭에서 데이터를 찾을 수 없습니다.")
            continue

        id_idx = find_id_index(header)
        if id_idx == -1:
            print(f"⚠️ {track} 탭에서 학번 컬럼을 찾을 수 없습니다. 건너뜁니다.")
            continue

        for row in rows:
            if len(row) <= id_idx:
                continue
            sid = str(row[id_idx]).strip()
            if not sid or not sid.isdigit():
                continue

            score = extract_score(row, header)
            name = ""
            # 이름 컬럼 찾기
            for i, h in enumerate(header):
                if "이름" in str(h) or "name" in str(h).lower() or "성명" in str(h):
                    if len(row) > i:
                        name = str(row[i]).strip()
                    break

            students[sid] = {
                "name": name,
                "track": track,
                "기말": score,
                "중간": 0.0,
                "과제_이메일": 0.0,
                "과제_상호평가": 0.0,
                "수업태도": 0.0,
            }
        print(f"✅ {track} 분반(기말고사 데이터) {len(rows)}건 처리 완료")

    # 2. 추가 데이터 탭 수집
    extra_tabs = ["중간고사", "과제_이메일", "과제_상호평가", "수업태도"]
    for tab in extra_tabs:
        header, rows = read_sheet_data(service, SPREADSHEET_ID, tab)
        if not rows:
            continue

        id_idx = find_id_index(header)
        if id_idx == -1:
            print(f"⚠️ {tab} 탭에서 학번 컬럼을 찾을 수 없습니다.")
            continue

        matched_count = 0
        for row in rows:
            if len(row) <= id_idx:
                continue
            sid = str(row[id_idx]).strip()
            if sid in students:
                score = extract_score(row, header)
                students[sid][tab] = score
                matched_count += 1
        print(f"✅ {tab} 데이터 병합 완료: {matched_count}명 매칭됨")

    # 3. 최종 점수 계산
    # Python반(468) : 기말 40, 과제 30, 참여 20, 중간 10
    # Web반(761, 762) : 기말 40, 과제 20, 참여 20, 중간 20
    final_results = []

    # 헤더 구성
    out_header = [
        "분반",
        "학번",
        "이름",
        "기말",
        "중간",
        "과제_이메일",
        "과제_상호평가",
        "수업태도",
        "최종점수",
    ]

    for sid, data in students.items():
        track = data["track"]
        final_exam = data["기말"]
        midterm = data["중간"]
        hw_email = data["과제_이메일"]
        hw_peer = data["과제_상호평가"]
        attitude = data["수업태도"]

        total_hw = hw_email + hw_peer

        # NOTE: 이 스크립트는 입력된 각 항목의 점수가 100점 만점 기준이라고 가정하고 가중치를 곱합니다.

        if track == "468":  # Python
            final_score = (
                (final_exam * 0.4)
                + (midterm * 0.1)
                + (total_hw * 0.3)
                + (attitude * 0.2)
            )
        else:  # Web (761, 762)
            final_score = (
                (final_exam * 0.4)
                + (midterm * 0.2)
                + (total_hw * 0.2)
                + (attitude * 0.2)
            )

        final_score = round(final_score, 2)

        final_results.append(
            [
                track,
                sid,
                data["name"],
                final_exam,
                midterm,
                hw_email,
                hw_peer,
                attitude,
                final_score,
            ]
        )

    # 학번 순 정렬
    final_results.sort(key=lambda x: x[1])

    # 4. 결과 시트에 쓰기
    TARGET_TAB_NAME = "최종 성적 통합"

    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get("sheets", [])
    target_sheet_id = None

    for s in sheets:
        if s.get("properties", {}).get("title") == TARGET_TAB_NAME:
            target_sheet_id = s.get("properties", {}).get("sheetId")
            break

    if target_sheet_id is None:
        print(f"📝 '{TARGET_TAB_NAME}' 탭이 없어서 새로 생성합니다.")
        batch_update_request = {
            "requests": [{"addSheet": {"properties": {"title": TARGET_TAB_NAME}}}]
        }
        (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=SPREADSHEET_ID, body=batch_update_request)
            .execute()
        )

    body = {"values": [out_header] + final_results}
    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{TARGET_TAB_NAME}'!A1",
            valueInputOption="USER_ENTERED",
            body=body,
        )
        .execute()
    )

    print(
        f"🎉 성공적으로 {len(final_results)}명의 성적을 '{TARGET_TAB_NAME}' 탭에 기록했습니다."
    )


if __name__ == "__main__":
    main()
