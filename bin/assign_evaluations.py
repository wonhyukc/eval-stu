#!/usr/bin/env python3
import sys
import os
import csv
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.match_assigner import build_master_roster, assign_peers_for_class
from modules.assignment_validator import validate_assignment_csv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEET_ID = "1_o-F6UaQ2WOe0nH2zuT_0xpwiOm1ebmWo2sEQzQptEk"


def get_submitted_students():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    secret_path = os.path.join(base_dir, "gwsServiceAccnt-mail.json")

    try:
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"❌ 인증 실패: {e}", file=sys.stderr)
        raise e

    sheet_metadata = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    first_sheet_title = sheet_metadata["sheets"][0]["properties"]["title"]

    range_name = f"{first_sheet_title}!A:Z"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SHEET_ID, range=range_name)
        .execute()
    )
    values = result.get("values", [])

    if not values:
        return []

    headers = values[0]
    hakbun_idx = -1
    for i, h in enumerate(headers):
        if "학번" in str(h) or "ID" in str(h):
            hakbun_idx = i
            break

    if hakbun_idx == -1:
        print(
            "❌ 시트에서 학번 컬럼을 찾을 수 없습니다. 컬럼들: " + ", ".join(headers),
            file=sys.stderr,
        )
        return []

    submitted_ids = []
    for row in values[1:]:
        if len(row) > hakbun_idx:
            val = str(row[hakbun_idx]).strip()
            if val:
                # 숫자만 추출하거나 있는 그대로 사용
                submitted_ids.append(val)

    return list(set(submitted_ids))


def main():
    print("🔄 구글 시트에서 제출자 명단을 가져오는 중...")
    try:
        submitted_ids = get_submitted_students()
        print(f"✅ 구글 시트에서 총 {len(submitted_ids)}명의 제출자를 확인했습니다.")
    except Exception as e:
        print(f"❌ 구글 시트 접속 또는 데이터 파싱 에러: {e}", file=sys.stderr)
        sys.exit(1)

    print("�� 마스터 명단을 읽어오는 중...")
    roster_dict = build_master_roster()
    if not roster_dict:
        print(
            "💡 입력 파일(input/students/*.md)에서 데이터를 찾을 수 없습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    class_evaluators = defaultdict(list)
    class_targets = defaultdict(list)

    for s_id, student in roster_dict.items():
        c_num = student["강좌번호"]
        class_evaluators[c_num].append(student)
        if s_id in submitted_ids:
            class_targets[c_num].append(student)

    # 데이터 통계 확인용 출력
    for c_num in class_evaluators.keys():
        print(
            f"  - 분반 {c_num}: 전체 평가자 {len(class_evaluators[c_num])}명, 제출(대상)자 {len(class_targets[c_num])}명"
        )

    output_path = os.path.join("output", "peer-eval-result.csv")
    os.makedirs("output", exist_ok=True)

    print("🔄 매칭 알고리즘 수행 중...")
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.write(
            "분반,평가자_학번,평가자_이름,피평가자1_학번,피평가자1_이름,피평가자2_학번,피평가자2_이름,피평가자3_학번,피평가자3_이름\n"
        )

        for c_num in sorted(class_evaluators.keys()):
            evaluators = class_evaluators[c_num]
            targets = class_targets[c_num]

            assignments = assign_peers_for_class(evaluators, targets, 3)

            for t_id, assigned_targets in assignments.items():
                evaluator_student = roster_dict[t_id]
                padded = assigned_targets + [{"학번": "", "이름": ""}] * (
                    3 - len(assigned_targets)
                )

                row_vals = [
                    str(c_num),
                    str(evaluator_student["학번"]),
                    str(evaluator_student["이름"]),
                    str(padded[0]["학번"]),
                    str(padded[0]["이름"]),
                    str(padded[1]["학번"]),
                    str(padded[1]["이름"]),
                    str(padded[2]["학번"]),
                    str(padded[2]["이름"]),
                ]
                out_f.write(",".join(row_vals) + "\n")

    print(f"✅ 매칭 결과가 성공적으로 생성되었습니다: {output_path}")
    print("\n🔄 매칭 결과 검증 로직을 실행합니다...")
    validate_assignment_csv(output_path)


if __name__ == "__main__":
    main()
