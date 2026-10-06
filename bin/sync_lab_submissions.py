#!/usr/bin/env python3
"""
실습(Lab) 과제 제출 데이터 동기화 및 중복 제거 도구
(SSOT: 1docs/score-lab.md)

1인 1건 원칙:
- 마감 전 제출 이력이 있는 경우: 마감 시각 전 가장 마지막(최신) 제출본 유효 (On-time)
- 마감 후에만 제출한 경우: 마감 후 제출물 중 가장 마지막(최신) 제출본 유효 (Late)
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.lab_submission_parser import (
    deduplicate_submissions,
    get_course_deadline,
)
from modules.match_assigner import parse_markdown_table
from modules.sheet_updater import get_sheet_service

SPREADSHEET_ID_SOURCE = "1_o-F6UaQ2WOe0nH2zuT_0xpwiOm1ebmWo2sEQzQptEk"
SHEET_RANGE_SOURCE = "설문지 응답 시트3!A:I"

COURSE_CONFIG = {
    "py": {
        "sheet_id": "1Ni4ZaeIJJdNNvysx5-LFpOF6sh4Emp-cK92DnTUsAyQ",
        "tab_name": "상호평가 제출자 답",
        "roster_file": "5input/students/py-students.md",
        "track_id": "14712",
        "track_code": "04",
    },
    "web1": {
        "sheet_id": "1pVbDITgW07ErTS4sQHDt1edVDCVKXrLAeRG3fF7-fAk",
        "tab_name": "peer-eval-submissions",
        "roster_file": "5input/students/wb-students.md",
        "track_id": "15143",
        "track_code": "01",
    },
    "web2": {
        "sheet_id": "1OMeWuYt45TZMygmkh5hOhqSCCUFYJv4iE0hTY554iAo",
        "tab_name": "peer-eval-submissions",
        "roster_file": "5input/students/wb-students.md",
        "track_id": "15144",
        "track_code": "02",
    },
}


def main():
    parser = argparse.ArgumentParser(
        description="실습 과제 제출본 중복제거 및 시트 동기화 도구"
    )
    parser.add_argument(
        "--course",
        type=str,
        default="py",
        choices=["py", "web1", "web2"],
        help="과목 분반 (py, web1, web2)",
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="특정 주차 필터링 (미지정 시 전체 주차 반영)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="대상 구글 스프레드시트 탭에 즉시 동기화",
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = COURSE_CONFIG[args.course]

    roster_path = os.path.join(base_dir, cfg["roster_file"])
    if not os.path.exists(roster_path):
        print(f"❌ 명단 파일을 찾을 수 없습니다: {roster_path}")
        sys.exit(1)

    all_students = parse_markdown_table(roster_path)
    target_students = [
        s for s in all_students if str(s.get("강좌번호", "")).strip() == cfg["track_id"]
    ]

    print(f"📋 [{args.course}] 전체 수강생: {len(target_students)}명 로드 완료")

    service = get_sheet_service(base_dir)
    res = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID_SOURCE, range=SHEET_RANGE_SOURCE)
        .execute()
    )
    rows = res.get("values", [])
    if not rows:
        print("❌ 설문지 원본 시트에 데이터가 없습니다.")
        sys.exit(1)

    # 주차별 마감 계산 및 중복 제거
    # 주차가 지정된 경우 해당 주차 마감 사용, 미지정 시 각 행별 주차에 맞춤
    if args.week:
        deadline = get_course_deadline(args.course, args.week, base_dir)
        valid_submissions = deduplicate_submissions(
            rows[1:], target_students, deadline=deadline, week_filter=args.week
        )
    else:
        # 전체 주차 대상: 주차별로 그룹화하여 처리
        valid_submissions = []
        weeks = {
            str(int(r[5].strip()))
            for r in rows[1:]
            if len(r) > 5 and str(r[5]).strip().isdigit()
        }
        for w in sorted(weeks, key=lambda x: int(x)):
            dl = get_course_deadline(args.course, w, base_dir)
            w_valid = deduplicate_submissions(
                rows[1:], target_students, deadline=dl, week_filter=w
            )
            valid_submissions.extend(w_valid)

    valid_submissions.sort(key=lambda x: (x["week"], x["student_id"]))

    print(f"\n🎯 유효 제출본 ({len(valid_submissions)}건 확정):")
    for idx, v in enumerate(valid_submissions, 1):
        print(
            f"  {idx:2d}. [Week {v['week']}] {v['student_id']} ({v['student_name']}) | "
            f"{v['status']} (시도 {v['total_attempts']}회) | {v['timestamp']} | {v['url'][:45]}..."
        )

    if args.sync:
        sheet_id = cfg["sheet_id"]
        tab_name = cfg["tab_name"]

        formatted_rows = []
        for v in valid_submissions:
            raw = v["raw_row"]
            formatted_rows.append(
                [
                    raw[0] if len(raw) > 0 else "",
                    raw[1] if len(raw) > 1 else "",
                    f"'{str(v['student_id'])[-3:]}",
                    v["url"],
                    v["commit"],
                    str(v["week"]),
                    cfg["track_code"],
                    "",  # 개인정보 보호: 이름 제외
                    raw[8] if len(raw) > 8 else "",
                ]
            )

        # Clear
        clear_range = f"'{tab_name}'!A2:I"
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range=clear_range
        ).execute()

        # Update
        update_range = f"'{tab_name}'!A2:I{1 + len(formatted_rows)}"
        body = {"values": formatted_rows}
        update_res = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=sheet_id,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body=body,
            )
            .execute()
        )
        print(f"\n✅ '{tab_name}' 탭에 {update_res.get('updatedRows')}행 동기화 완료!")


if __name__ == "__main__":
    main()
