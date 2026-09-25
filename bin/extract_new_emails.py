import sys
import os
import csv
import re
from datetime import datetime, timezone, timedelta
import email.utils

sys.path.append(os.getcwd())
from modules.mail_fetcher import fetch_assignment_emails


def parse_students():
    name_to_id = {}
    id_to_track = {}
    for filepath in ["input/students/py-students.md", "input/students/wb-students.md"]:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("|") or "---" in line or "학번" in line:
                        continue
                    cols = [c.strip() for c in line.split("|")]
                    if len(cols) > 8:
                        track = cols[1]
                        student_id = cols[3]
                        eng_name = cols[4]
                        kor_name = cols[8]

                        if student_id.isdigit():
                            id_to_track[student_id] = track
                            clean_eng = re.sub(r"\s+", "", eng_name).lower()
                            if clean_eng:
                                name_to_id[clean_eng] = student_id
                            clean_kor = re.sub(r"\s+", "", kor_name)
                            if clean_kor:
                                name_to_id[clean_kor] = student_id

                            email_addr = cols[5].lower()
                            name_to_id[email_addr] = student_id
    return name_to_id, id_to_track


def load_deadlines():
    KST = timezone(timedelta(hours=9))
    deadlines = {}
    dl_path = "input/deadline.csv"
    if os.path.exists(dl_path):
        with open(dl_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 2 and parts[0].isdigit():
                    week = int(parts[0])
                    date_str = parts[1].strip()
                    if date_str:
                        try:
                            dt = datetime.strptime(f"2026/{date_str}", "%Y/%m/%d %H:%M")
                            dt = dt.replace(tzinfo=KST)
                            deadlines[week] = dt
                        except ValueError:
                            pass
    return deadlines


def main():
    name_to_id, id_to_track = parse_students()
    deadlines = load_deadlines()

    processed_keys = set()
    try:
        if os.path.exists("score1.csv"):
            with open("score1.csv", "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    t = row.get("메일제목", "").strip()
                    d = row.get("날짜", "").strip()
                    processed_keys.add(f"{t}|{d}")
    except Exception as e:
        print("Could not read score1.csv:", e)
        return

    print(f"Loaded {len(processed_keys)} processed emails.")

    print("Fetching emails after 2026/04/01...")
    new_emails = fetch_assignment_emails("after:2026/04/01", max_results=500)
    print(f"Fetched {len(new_emails)} emails.")

    # strict rules will be compiled dynamically per week
    format_re = re.compile(
        r"(과제|assignment|homework)0?\.(\d+)(?:\[|\()?(\d{10})(?:\]|\))?"
    )
    week_re = re.compile(r"(과제|assignment|homework|week)0?\.?(\d+)")

    type_re = re.compile(r"(0\.[1-9])")

    new_rows = []

    for email_data in new_emails:
        subject = email_data["subject"].strip()
        date_str = email_data["date_str"].strip()
        sender = email_data["sender"].strip()

        if f"{subject}|{date_str}" in processed_keys:
            continue

        row = {
            "no": "",
            "학번": "",
            "추정하는학번": "",
            "track": "",
            "점수": "",
            "유형": "",
            "이유": "",
            "날짜": date_str,
            "이름": sender,
            "메일제목": subject,
        }

        sender_name = sender.split("<")[0].strip()
        sender_email = ""
        if "<" in sender and ">" in sender:
            start_idx = sender.find("<") + 1
            end_idx = sender.find(">")
            sender_email = sender[start_idx:end_idx]

        clean_name = re.sub(r"\s+", "", sender_name).lower()
        est_id = ""
        if clean_name in name_to_id:
            est_id = name_to_id[clean_name]
        elif sender_email in name_to_id:
            est_id = name_to_id[sender_email]
        else:
            m = re.search(r"\d{10}", subject)
            if m:
                est_id = m.group(0)

        row["추정하는학번"] = est_id
        if est_id in id_to_track:
            row["track"] = id_to_track[est_id]

        email_type = ""
        type_match = type_re.search(subject)
        if type_match:
            email_type = type_match.group(1)

        ff_score = 0
        if "공유 요청" in subject:
            ff_score = 1
            email_type = "first finder"

        row["유형"] = email_type

        format_score = 0
        deadline_score = 0
        week_num = None

        clean_sub = re.sub(r"\s+", "", subject.lower())

        type_float = 0.0
        try:
            if email_type:
                type_float = float(email_type)
        except ValueError:
            pass

        if type_float >= 0.5:
            week_num = int(type_float * 10)
            track_num = row["track"]
            is_valid_format = False

            week_str = email_type.replace(".", r"\.").replace(",", r"[,.]")
            strict_py_re = re.compile(
                f"과제{week_str}(?:\\[|\\()?(\\d{{10}})(?:\\]|\\))?"
            )
            strict_wb_re = re.compile(
                f"assignment{week_str}(?:\\[|\\()?(\\d{{10}})(?:\\]|\\))?"
            )

            if track_num == "468":
                if strict_py_re.search(clean_sub):
                    is_valid_format = True
            elif track_num in ("761", "762"):
                if strict_wb_re.search(clean_sub):
                    is_valid_format = True
            else:
                if strict_py_re.search(clean_sub) or strict_wb_re.search(clean_sub):
                    is_valid_format = True

            if is_valid_format:
                format_score = 1
        elif ff_score == 0:
            m_format = format_re.search(clean_sub)
            if m_format:
                format_score = 1
                week_num = int(m_format.group(2))
            else:
                m_week = week_re.search(clean_sub)
                if m_week:
                    week_num = int(m_week.group(2))

        email_dt = None
        try:
            email_dt = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            pass

        if week_num is not None and week_num in deadlines and email_dt is not None:
            if email_dt <= deadlines[week_num]:
                deadline_score = 1

        row_score = format_score + deadline_score + ff_score

        reasons = []
        if ff_score > 0:
            reasons.append("FirstFinder(+1)")
        if format_score > 0:
            reasons.append("제목양식(+1)")
        if deadline_score > 0:
            reasons.append("기한내(+1)")

        if reasons:
            row["이유"] = " ".join(reasons)

        row["점수"] = row_score

        new_rows.append(row)

    print(f"Found {len(new_rows)} new emails to save.")

    if new_rows:
        fieldnames = [
            "no",
            "학번",
            "추정하는학번",
            "track",
            "점수",
            "유형",
            "이유",
            "날짜",
            "이름",
            "메일제목",
        ]
        with open("score2.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_rows)
        print("Saved to score2.csv")


if __name__ == "__main__":
    main()
