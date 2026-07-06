import csv
import os
from typing import Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

input_file = os.path.join(BASE_DIR, "5input", "python - score (2).csv")
out_hw = os.path.join(BASE_DIR, "output", "moodle_score_track_468_과제.tsv")
out_part = os.path.join(BASE_DIR, "output", "moodle_score_track_468_수업참여.tsv")

hw_scores: Dict[str, float] = {}
part_scores: Dict[str, float] = {}

with open(input_file, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        student_id = row.get("학번", "").strip()
        if not student_id or student_id == "학번없음":
            continue

        score_str = row.get("점수", "").strip()
        try:
            score = float(score_str)
        except ValueError:
            score = 0.0

        yuhyeong = row.get("유형", "").strip().lower()
        reason = row.get("이유", "").strip().lower()

        # 분류 로직: '수업참여', 'first finder', '질문'은 수업참여로. 나머지는 과제로.
        if (
            "수업참여" in yuhyeong
            or "first finder" in yuhyeong
            or ("질문" in reason and not yuhyeong)
        ):
            cat = "수업참여"
        else:
            cat = "과제"

        if cat == "과제":
            hw_scores[student_id] = hw_scores.get(student_id, 0.0) + score
        else:
            part_scores[student_id] = part_scores.get(student_id, 0.0) + score


# TSV 생성 함수 (Moodle 양식)
def write_tsv(filename, scores_dict):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["id", "score"])
        for sid, total_score in scores_dict.items():
            writer.writerow([sid, round(total_score, 2)])
    print(f"✅ {filename} 생성 완료 ({len(scores_dict)}명)")


write_tsv(out_hw, hw_scores)
write_tsv(out_part, part_scores)
