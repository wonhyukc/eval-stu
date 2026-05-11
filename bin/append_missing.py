import csv

all_file = "/home/hyuk/nvme_data/prj/stu/eval/input-sheet/students_all - 채점.csv"
web_file = "/home/hyuk/nvme_data/prj/stu/eval/input-sheet/web - score.csv"

# Step 1: Find missing records
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

# Step 2: Append missing records to web - score.csv
if missing:
    with open(web_file, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        for row in missing:
            # web - score.csv columns: no,학번,track,점수,유형,이유,날짜,이름,메일제목
            student_id = row.get("추정하는학번", "").strip()
            if not student_id:
                student_id = row.get("학번", "").strip()

            writer.writerow(
                [
                    row.get("no", ""),
                    student_id,
                    row.get("track", ""),
                    row.get("점수", ""),
                    row.get("유형", ""),
                    row.get("이유", ""),
                    row.get("날짜", ""),
                    row.get("이름", ""),
                    row.get("메일제목", ""),
                ]
            )
    print(f"Successfully appended {len(missing)} missing records to web - score.csv")
else:
    print("No missing records to append.")
