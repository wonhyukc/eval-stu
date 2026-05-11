#!/usr/bin/env python3
import sys
import os
import random
from collections import defaultdict
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from modules.match_assigner import parse_markdown_table

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEET_ID = "1_o-F6UaQ2WOe0nH2zuT_0xpwiOm1ebmWo2sEQzQptEk"


def assign_only_submitters(submitters, num_peers=3):
    # submitters: list of dicts: {"학번": ..., "이름": ..., "url": ...}
    if len(submitters) < 2:
        return {s["학번"]: [] for s in submitters}

    targets = list(submitters)
    random.shuffle(targets)
    assignments = {s["학번"]: [] for s in submitters}

    # Simple assignment logic for "only submitters evaluate each other"
    # Ensure each gets exactly num_peers
    n = len(submitters)
    for i, evaluator in enumerate(submitters):
        assigned = []
        for j in range(1, num_peers + 1):
            target_idx = (i + j) % n
            assigned.append(submitters[target_idx])
        assignments[evaluator["학번"]] = assigned

    return assignments


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    secret_path = os.path.join(base_dir, "secret.json")

    creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

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
        print("시트에 데이터가 없습니다.")
        return

    headers = values[0]
    hakbun_idx = -1
    url_idx = -1
    week_idx = -1

    for i, h in enumerate(headers):
        h_str = str(h)
        if "학번" in h_str or "Student ID" in h_str:
            hakbun_idx = i
        elif "GitHub Repository" in h_str:
            url_idx = i
        elif "주차 Week" in h_str:
            week_idx = i

    # deduplicate by latest timestamp for week 10
    submissions = {}
    for row in values[1:]:
        if len(row) <= max(hakbun_idx, url_idx, week_idx):
            continue
        week = str(row[week_idx]).strip()
        if week != "11":
            continue

        hakbun = str(row[hakbun_idx]).strip()
        url = str(row[url_idx]).strip()

        if hakbun and url:
            # We assume rows are ordered chronologically, so later rows overwrite earlier ones.
            # Thus, just overwriting is sufficient to keep the "latest".
            submissions[hakbun] = url

    # Load py students
    py_students = parse_markdown_table(
        os.path.join(base_dir, "input", "students", "py-students.md")
    )
    py_roster = {s["학번"]: s for s in py_students}

    # Filter submitters who are in py_roster
    py_submitters = []
    for s_id, url in submissions.items():
        if s_id in py_roster:
            student_info = py_roster[s_id]
            student_info["url"] = url
            py_submitters.append(student_info)

    print(f"✅ 11주차 py 제출자 수: {len(py_submitters)}명")

    # Assign peers (only submitters to each other)
    # Shuffle submitters to make random assignment
    random.shuffle(py_submitters)
    num_peers = min(3, len(py_submitters) - 1)

    assignments = assign_only_submitters(py_submitters, num_peers)

    # Write to Markdown
    out_md = os.path.join(base_dir, "output", "week11_peer_review_assignments_py.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(
            "# Week 11 Peer Review Assignments / 11주차 상호평가 배당표 (Track 468 / py)\n\n"
        )
        f.write("*사용자 규칙: 제출자만 서로 상호 평가하도록 배정되었습니다.*\n\n")
        f.write(
            "| Evaluator / 평가자 (학번) | Reviewee 1 / 피평가자 1 | Reviewee 2 / 피평가자 2 | Reviewee 3 / 피평가자 3 |\n"
        )
        f.write("| :--- | :--- | :--- | :--- |\n")

        for eval_student in sorted(py_submitters, key=lambda x: x["학번"]):
            eval_id = eval_student["학번"]
            targets = assignments[eval_id]
            row_cells = [f"**{eval_id}**"]

            for t in targets:
                row_cells.append(f"[{t['학번']}]({t['url']})")

            # Pad if needed
            while len(row_cells) < 4:
                row_cells.append("N/A")

            f.write("| " + " | ".join(row_cells) + " |\n")

    print(f"✅ 마크다운 생성 완료: output/week11_peer_review_assignments_py.md")


if __name__ == "__main__":
    main()
