import csv
import io
import os
from typing import Dict, Tuple

input_file = "/home/hyuk/nvme_data/prj/stu/eval/input-sheet/web - score.csv"

data: Dict[Tuple[str, str], Dict[str, float]] = {}

with open(input_file, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        track = row.get("track", "").strip()
        if track.endswith(".0"):
            track = track[:-2]

        if not track:
            continue

        student_id = row.get("학번", "").strip()
        if not student_id:
            continue

        yuhyeong = row.get("유형", "").strip()
        cat = "수업참여" if yuhyeong == "수업참여" else "과제"

        score_str = row.get("점수", "").strip()
        try:
            score = float(score_str)
        except ValueError:
            score = 0.0

        key = (track, cat)
        if key not in data:
            data[key] = {}

        data[key][student_id] = data[key].get(student_id, 0.0) + score

# Write files
output_files = []
for (track, cat), scores in data.items():
    out_f = f"/home/hyuk/nvme_data/prj/stu/eval/input-sheet/web_track_{track}_{cat}.tsv"
    with open(out_f, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["id", "score"])
        for sid in sorted(scores.keys()):
            writer.writerow([sid, round(scores[sid], 2)])
    output_files.append(out_f)

print(f"Total {len(output_files)} files created:")
for out_file in output_files:
    print(os.path.basename(out_file))
