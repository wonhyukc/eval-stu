#!/usr/bin/env python3
import sys
import os
import csv
import argparse
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from modules.peer_grader import build_track_map
from modules.match_assigner import parse_markdown_table

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json"
)


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        import json

        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--course", type=str, default="py", help="Course prefix (e.g. py, web)"
    )
    parser.add_argument(
        "-w", "--week", type=str, default="06", help="Week number (e.g. 05, 06)"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Use local CSV (output/sample_data.csv)"
    )
    parser.add_argument(
        "--upload", action="store_true", help="Upload graded results to Google Sheets"
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    secret_path = os.path.join(base_dir, "secret.json")

    settings = load_settings()
    sheet_id = settings.get(
        "evaluation_form_sheet_id", "166MzQg-W6r9GEynt1bOlr8hUex0Rvx6Yky2ffSVNtKM"
    )

    track_map = build_track_map(base_dir)
    print(f"DEBUG: sheet_id={sheet_id}")

    print(f"🚀 [상호평가 다수결 채점 엔진 시작] {args.course}-{args.week}")
    print(f"DEBUG: base_dir={base_dir}, secret_path={secret_path}")

    values = []
    if args.offline:
        csv_path = os.path.join(base_dir, "output", "sample_data.csv")
        print(f"📂 오프라인 모드: 로컬 CSV 읽기 ({csv_path})")
        if not os.path.exists(csv_path):
            print("❌ CSV 파일이 없습니다.")
            sys.exit(1)
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            values = list(reader)
    else:
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        target_gid = 1491146932
        sheet_title = None
        for s in sheet_metadata.get("sheets", []):
            if s["properties"].get("sheetId") == target_gid:
                sheet_title = s["properties"]["title"]
                break

        if not sheet_title:
            sheet_title = sheet_metadata.get("sheets", [])[0]["properties"]["title"]

        range_name = f"{sheet_title}!A:Z"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])

    if not values:
        print("💡 데이터가 없습니다.")
        return

    headers = values[0]
    evaluator_idx, target_idx = -1, -1
    week_idx = -1
    score_idxs = []

    for i, h in enumerate(headers):
        h_str = str(h)
        if (
            ("학번" in h_str or "Student ID" in h_str)
            and "평가자" in h_str
            and evaluator_idx == -1
        ):
            evaluator_idx = i
        elif "제출자" in h_str or "피평가자" in h_str or "Reviewee" in h_str:
            target_idx = i
        elif "평가 주차" in h_str or "Week" in h_str:
            week_idx = i
        elif "Q" in h_str and ("점수" in h_str or "Score" in h_str):
            score_idxs.append(i)

    if evaluator_idx == -1:
        evaluator_idx = 3
    if target_idx == -1:
        target_idx = 4
    if week_idx == -1:
        week_idx = 2
    if not score_idxs:
        score_idxs = [5, 6, 7, 8, 9, 10, 11, 12, 13]  # fallback

    # 1. Group data
    # evals_by_target = { target_id: [ (evaluator_id, scores_array), ... ] }
    # assigned_count = { evaluator_id: count } (How many evaluations they actually submitted)
    evals_by_target = {}
    assigned_count = {}

    # Track maximum observed score per question globally to deduce "Max Score"
    max_scores_per_q = [0.0] * len(score_idxs)

    week_num = str(int(args.week))  # "06" -> "6", "10" -> "10"
    print(f"🔍 필터링 주차 키워드: '{week_num}' (예: {week_num}주차, Week {week_num})")

    for row in values[1:]:
        if len(row) <= max(target_idx, week_idx):
            continue

        # 주차 필터링
        row_week = row[week_idx].strip()
        if not (
            f"{week_num}주차" in row_week
            or f"Week {week_num}" in row_week
            or row_week == week_num
        ):
            continue

        evaluator = row[evaluator_idx].strip()
        target = row[target_idx].strip()
        if not evaluator or not target:
            continue

        scores_given = []
        for i, idx in enumerate(score_idxs):
            val = (
                float(row[idx].strip())
                if len(row) > idx and row[idx].strip().replace(".", "", 1).isdigit()
                else 0.0
            )
            scores_given.append(val)
            if val > max_scores_per_q[i]:
                max_scores_per_q[i] = val

        evals_by_target.setdefault(target, []).append((evaluator, scores_given))
        assigned_count[evaluator] = assigned_count.get(evaluator, 0) + 1

    total_max_submission_score = sum(max_scores_per_q)
    if total_max_submission_score == 0:
        total_max_submission_score = 1.0  # prevent div zero

    # 2. Determine Majority and Evaluation Points
    evaluator_points = {
        e: 0.0 for e in assigned_count
    }  # How many points they earned for grading
    target_submission_score = {}  # Final evaluated score by majority

    for target, evals in evals_by_target.items():
        # count occurrences of each score array
        score_tuples = [tuple(s) for _, s in evals]
        counter = Counter(score_tuples)
        majority_scores, majority_count = counter.most_common(1)[0]

        has_majority = majority_count > (len(evals) // 2)

        # Tie Breaker fallback: if 2 people tied, we just generously use the one with higher sum
        if not has_majority:
            # Sort by sum of scores descending
            majority_scores = sorted(
                counter.keys(), key=lambda s: sum(s), reverse=True
            )[0]

        target_submission_score[target] = sum(majority_scores)

        for evaluator, scores in evals:
            if tuple(scores) == majority_scores:
                # Earn a piece of the 3 points
                pct_weight = 3.0 / assigned_count[evaluator]
                evaluator_points[evaluator] += pct_weight
            else:
                # Wrong! Gets 0 for this piece.
                pass

    # 3. Calculate Final Combined Score
    # For every student found in either target or evaluator pool
    all_students = set(target_submission_score.keys()).union(
        set(evaluator_points.keys())
    )

    roster_course = "wb" if args.course == "web" else args.course
    md_path = os.path.join(
        base_dir, "5input", "students", f"{roster_course}-students.md"
    )
    roster_data = []
    if os.path.exists(md_path):
        roster_data = parse_markdown_table(md_path)
        valid_students = {row.get("학번", "") for row in roster_data if row.get("학번")}
        all_students = all_students.intersection(valid_students)
        print(
            f"📊 {args.course} 트랙 학생 명부 {len(valid_students)}명 기준 교집합 필터링: {len(all_students)}명 대상"
        )

    final_results = []
    for sid in all_students:
        s_score = target_submission_score.get(sid, 0.0)
        e_score = evaluator_points.get(sid, 0.0)

        # Submission weight 0.8
        sub_ratio = (s_score / total_max_submission_score) * 0.8

        # Evaluator weight 0.2 (Max 3 points)
        eval_ratio = (min(e_score, 3.0) / 3.0) * 0.2

        total_score = sub_ratio + eval_ratio

        final_results.append(
            {
                "분반": track_map.get(sid, ""),
                "학번": sid,
                "제출점수(가중치0.8)": round(sub_ratio, 3),
                "평가점수(가중치0.2)": round(eval_ratio, 3),
                "최종획득점수(1.0만점)": round(total_score, 3),
                "수신받은원본총점": s_score,
                "배정대비달성도": round(e_score, 1),
            }
        )

    # 동일 제출자별로 정렬
    final_results.sort(key=lambda x: x["학번"])

    output_filename = f"{args.course}-{args.week}-peer-score.csv"
    output_path = os.path.join(base_dir, "output", output_filename)

    # Save to CSV
    # Ensure output exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "분반",
                "학번",
                "제출점수(가중치0.8)",
                "평가점수(가중치0.2)",
                "최종획득점수(1.0만점)",
                "수신받은원본총점",
                "배정대비달성도",
            ],
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        writer.writerows(final_results)

    print(f"✅ 채점 완료. 결과 저장됨: {output_path}")
    print(f"   => 저장 대상 학생 수: {len(final_results)}명")

    # 4. 구글 시트 자동 업로드 (--upload 옵션 지정 시)
    if getattr(args, "upload", False):
        print("\n⬇️ 이제 추출된 데이터를 시트에 실제 기록(Append)합니다 ⬇️")
        from datetime import datetime
        from modules.sheet_updater import append_grades_to_sheet

        roster_by_sid = {}
        if roster_data:
            for row in roster_data:
                if row.get("학번"):
                    roster_by_sid[row["학번"]] = row.get("이름", "")

        rows_to_append = []
        today_str = datetime.today().strftime("%Y-%m-%d")
        week_type = str(int(args.week))
        reason_str = f"PeerEval{week_type}"

        for res in final_results:
            sid = res["학번"]
            track = res["분반"]
            score = res["최종획득점수(1.0만점)"]
            name = roster_by_sid.get(sid, "")

            # format: [no, 학번, track/트랙, 점수, 유형, 이유, 날짜, 이름, 메일제목]
            rows_to_append.append(
                [
                    "",  # no (자동 할당)
                    sid,
                    track,
                    score,
                    week_type,  # 유형
                    reason_str,  # 이유
                    today_str,  # 날짜
                    name,  # 이름
                    "Peer Evaluation",  # 메일제목
                ]
            )

        if rows_to_append:
            success = append_grades_to_sheet(rows_to_append, course=args.course)
            if success:
                print(f"✅ {args.course} {args.week}주차 상호평가 시트 업로드 성공!")
            else:
                print(f"❌ {args.course} {args.week}주차 상호평가 시트 업로드 실패!")
        else:
            print("❗ 시트에 추가할 데이터가 없습니다.")


if __name__ == "__main__":
    main()
