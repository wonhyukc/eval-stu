import csv

all_file = "/home/hyuk/nvme_data/prj/stu/eval/input-sheet/students_all - 채점.csv"
web_file = "/home/hyuk/nvme_data/prj/stu/eval/input-sheet/web - score.csv"

web_nos = set()
with open(web_file, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        no = row.get("no", "").strip()
        if no:
            web_nos.add(no)

missing = []
with open(all_file, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        no = row.get("no", "").strip()
        if not no:
            continue

        score_str = row.get("점수", "").strip()
        try:
            score = float(score_str)
        except ValueError:
            score = 0.0

        if score > 0 and no not in web_nos:
            missing.append(row)

with open(
    "/home/hyuk/nvme_data/prj/stu/eval/missing_scores.md", "w", encoding="utf-8"
) as out:
    out.write("# 누락된 항목 목록\n\n")
    if not missing:
        out.write("점수가 0이 아니면서 누락된 항목이 없습니다!\n")
    else:
        out.write(
            f"**총 {len(missing)}개**의 유효한 점수 항목이 `web - score.csv`에서 누락되었습니다.\n\n"
        )
        out.write("| No | 학번 | 점수 | 유형 | 이름 | 메일제목 |\n")
        out.write("|---|---|---|---|---|---|\n")
        for row in missing:
            student_id = row.get("추정하는학번", "").strip()
            if not student_id:
                student_id = row.get("학번", "").strip()
            out.write(
                f"| {row['no']} | {student_id} | {row['점수']} | "
                f"{row.get('유형', '')} | {row.get('이름', '')} | "
                f"{row.get('메일제목', '')} |\n"
            )
print("missing_scores.md created.")
