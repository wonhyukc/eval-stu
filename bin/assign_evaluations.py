#!/usr/import sys
import os
import random
import json
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from modules.match_assigner import parse_markdown_table

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def assign_only_submitters(submitters, num_peers=3):
    if len(submitters) < 2:
        return {s["학번"]: [] for s in submitters}

    targets = list(submitters)
    random.shuffle(targets)
    assignments = {s["학번"]: [] for s in submitters}

    n = len(submitters)
    for i, evaluator in enumerate(submitters):
        assigned = []
        for j in range(1, num_peers + 1):
            target_idx = (i + j) % n
            assigned.append(submitters[target_idx])
        assignments[evaluator["학번"]] = assigned

    return assignments


def main():
    parser = argparse.ArgumentParser(description="상호평가 자동 배정 시스템")
    parser.add_argument("-c", "--c", "--course", dest="course", type=str, default="py", help="과정 (py, web)")
    parser.add_argument("-w", "--w", "--week", dest="week", type=str, required=True, help="주차 (예: 11)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    secret_path = os.path.join(base_dir, "secret.json")
    
    if not os.path.exists(secret_path):
        # fallback for old name if needed
        secret_path = os.path.join(base_dir, "gwsServiceAccnt-mail.json")

    settings = load_settings()
    sheet_id = settings.get("assignment_form_sheet_id", "1_o-F6UaQ2WOe0nH2zuT_0xpwiOm1ebmWo2sEQzQptEk")
    
    course_config = settings.get("courses", {}).get(args.course)
    if not course_config:
        print(f"❌ 설정 오류: settings.json에 '{args.course}' 과정 설정이 없습니다.")
        return
        
    allowed_tracks = course_config.get("tracks", [])

    print(f"🔄 구글 시트({sheet_id})에서 {args.week}주차 제출자 명단을 가져오는 중...")
    creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    first_sheet_title = sheet_metadata["sheets"][0]["properties"]["title"]

    range_name = f"{first_sheet_title}!A:Z"
    result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_name).execute()
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
        elif "주차" in h_str and "week" in h_str.lower():
            week_idx = i

    submissions = {}
    for row in values[1:]:
        if len(row) <= max(hakbun_idx, url_idx, week_idx):
            continue
        week = str(row[week_idx]).strip()
        if week != args.week:
            continue

        hakbun = str(row[hakbun_idx]).strip()
        url = str(row[url_idx]).strip()

        if hakbun and url:
            submissions[hakbun] = url

    # 마스터 명단 로드
    roster_file = f"5input/students/{args.course}-students.md"
    roster_path = os.path.join(base_dir, roster_file)
    if not os.path.exists(roster_path):
        roster_path = os.path.join(base_dir, "input", "students", f"{args.course}-students.md")

    students_list = parse_markdown_table(roster_path)
    
    for track in allowed_tracks:
        roster = {
            s["학번"]: s for s in students_list if str(s.get("강좌번호", "")).strip() == track
        }
        
        submitters = []
        for s_id, url in submissions.items():
            if s_id in roster:
                student_info = roster[s_id]
                student_info["url"] = url
                submitters.append(student_info)
                
        print(f"✅ {args.week}주차 {args.course} 트랙 {track} 제출자 수: {len(submitters)}명")

        if not submitters:
            print(f"⚠️ {track} 분반에 제출자가 없어 건너뜁니다.")
            continue

        random.shuffle(submitters)
        num_peers = min(3, len(submitters) - 1)

        assignments = assign_only_submitters(submitters, num_peers)

        out_md = os.path.join(base_dir, "9output", f"week{args.week}_peer_review_assignments_{track}.md")
        os.makedirs(os.path.dirname(out_md), exist_ok=True)
        
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(f"# Week {args.week} Peer Review Assignments / {args.week}주차 상호평가 배당표 (Track {track} / {args.course})\n\n")
            f.write("*사용자 규칙: 제출자만 서로 상호 평가하도록 배정되었습니다.*\n\n")
            f.write("| Evaluator / 평가자 (학번) | Reviewee 1 / 피평가자 1 | Reviewee 2 / 피평가자 2 | Reviewee 3 / 피평가자 3 |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")

            for eval_student in sorted(submitters, key=lambda x: x["학번"]):
                eval_id = eval_student["학번"]
                targets = assignments[eval_id]
                row_cells = [f"**{eval_id}**"]

                for t in targets:
                    row_cells.append(f"[{t['학번']}]({t['url']})")

                while len(row_cells) < 4:
                    row_cells.append("N/A")

                f.write("| " + " | ".join(row_cells) + " |\n")

        print(f"✅ 마크다운 생성 완료: {out_md}")

if __name__ == "__main__":
    main()
