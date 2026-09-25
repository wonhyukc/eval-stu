import csv
import re
from datetime import datetime, timezone, timedelta
import email.utils
import sys


def normalize_name_parts(name):
    """괄호 안 내용이나 특수문자를 제거하고, 이름 단어들을 추출하여 Set으로 반환"""
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"\[.*?\]", " ", name)
    name = re.sub(r"[^\w\s]", " ", name)
    return {p for p in name.lower().split() if p}


def parse_students(filepath):
    students = {}
    name_to_id = {}
    name_parts_to_id = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or "---" in line or "학번" in line:
                continue
            cols = [c.strip() for c in line.split("|")]
            if len(cols) > 8:
                student_id = cols[3]
                eng_name = cols[4]
                kor_name = cols[8]

                if student_id.isdigit():
                    students[student_id] = {"eng": eng_name, "kor": kor_name}

                    # Store mappings
                    clean_eng = re.sub(r"\s+", "", eng_name).lower()
                    if clean_eng:
                        name_to_id[clean_eng] = student_id
                    clean_kor = re.sub(r"\s+", "", kor_name)
                    if clean_kor:
                        name_to_id[clean_kor] = student_id

                    # Store parts mappings for fuzzy matching
                    eng_parts = normalize_name_parts(eng_name)
                    if eng_parts:
                        name_parts_to_id.append((eng_parts, student_id))
    return students, name_to_id, name_parts_to_id


def main():
    import json
    import os

    # 1. Load students
    students = {}
    name_to_id = {}
    name_parts_to_id = []
    for f in ["input/students/py-students.md", "input/students/wb-students.md"]:
        try:
            s, n2i, p2i = parse_students(f)
            students.update(s)
            name_to_id.update(n2i)
            name_parts_to_id.extend(p2i)
        except Exception as e:
            print(f"Error loading {f}: {e}")

    # Load manual mappings cache if exists
    manual_mappings = {}
    if os.path.exists("input/manual_mapping.json"):
        try:
            with open("input/manual_mapping.json", "r", encoding="utf-8") as f:
                manual_mappings = json.load(f)
        except Exception as e:
            print(f"Error loading manual mappings: {e}")

    # Add any manual mappings or emails already having IDs to name_to_id just in case
    # 2. Load deadline
    KST = timezone(timedelta(hours=9))
    deadlines = {}
    try:
        with open("input/deadline.csv", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 2 and parts[0].isdigit():
                    week = int(parts[0])
                    date_str = parts[1].strip()
                    if date_str:
                        try:
                            # e.g. "3/29 0:00" -> 2026/3/29
                            dt = datetime.strptime(f"2026/{date_str}", "%Y/%m/%d %H:%M")
                            dt = dt.replace(tzinfo=KST)
                            deadlines[week] = dt
                        except ValueError:
                            pass
    except FileNotFoundError:
        print(
            "Warning: input/deadline.csv not found. Deadline checking will be skipped."
        )

    # 3. Load emails
    emails = []
    with open("students_all - all_emails.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            emails.append(row)

    # regex patterns
    # strict format: (과제|assignment|homework) 0.X (10 digits)
    format_re = re.compile(
        r"(?i)(과제|assignment|homework)\s*0?\.(\d+)\s*(?:\[|\()?(\d{10})(?:\]|\))?"
    )
    # loose week extraction if strict fails:
    week_re = re.compile(r"(?i)(과제|assignment|homework|week)\s*0?\.?(\d+)")

    # 4. Process emails
    for row in emails:
        # Fill missing ID
        cur_id = row["학번"].strip()
        est_id = row["추정하는 학번"].strip()
        name = row["이름"].strip()
        clean_name = re.sub(r"\s+", "", name).lower()

        if not cur_id and not est_id:
            # First check manual mapping
            if clean_name in manual_mappings:
                row["추정하는 학번"] = manual_mappings[clean_name]
            # Then exact match
            elif clean_name in name_to_id:
                row["추정하는 학번"] = name_to_id[clean_name]
            else:
                # Fuzzy match using name parts
                email_parts = normalize_name_parts(name)
                best_match = None
                best_score = 0
                for s_parts, s_id in name_parts_to_id:
                    intersect = email_parts.intersection(s_parts)
                    score = len(intersect)
                    if score > 0 and score > best_score:
                        best_score = score
                        best_match = s_id

                # 단어 수가 2개 이상 일치하거나, 이메일 닉네임이 한 단어인데 일치하면 학번 추정
                if best_score >= 2 or (len(email_parts) == 1 and best_score == 1):
                    row["추정하는 학번"] = best_match

        effective_id = row["학번"].strip() or row["추정하는 학번"].strip()
        row["_effective_id"] = effective_id

        # Parse date
        date_str = row["날짜"]
        email_ts = 0
        email_dt = None
        try:
            email_dt = email.utils.parsedate_to_datetime(date_str)
            email_ts = email_dt.timestamp()
        except Exception:
            pass
        row["_ts"] = email_ts
        row["_dt"] = email_dt

        title = row["메일제목"].replace("\n", " ")
        email_type = row["type"].strip().lower()

        # Initialize scores for this row
        format_score = 0
        deadline_score = 0
        ff_score = 0
        week = None

        # Check first finder
        if (
            "first finder" in email_type
            or "first finder" in row["점수"]
            or "공유 요청" in title
        ):
            ff_score = 1
            if "first finder" not in email_type:
                row["type"] = "first finder"

        # Check title formatting and week
        m_format = format_re.search(title)
        if m_format:
            format_score = 1
            week = int(m_format.group(2))
        else:
            m_week = week_re.search(title)
            if m_week:
                week = int(m_week.group(2))

        row["_week"] = week

        # Check deadline
        if week is not None and week in deadlines and email_dt is not None:
            if email_dt <= deadlines[week]:
                deadline_score = 1

        row["_format_score"] = format_score
        row["_deadline_score"] = deadline_score
        row["_ff_score"] = ff_score
        row["_row_score"] = format_score + deadline_score + ff_score

    # 5. Handle duplicates (latest one per student per week)
    # We group by (effective_id, week).
    # If week is None (e.g. self introduction), we group by title or individually.
    # Instruction says: "같은 제목 중복된 메일 이 있는 지 파악해줘" -> deduplicate by exact title.
    # Instruction 2: "동일 학번 동일 과제 1건만"

    # We will keep track of the maximum _ts for (effective_id, week)
    latest_ts_for_assignment = {}
    for row in emails:
        eid = row["_effective_id"]
        w = row["_week"]
        if eid and w is not None:
            key = (eid, w)
            if key not in latest_ts_for_assignment:
                latest_ts_for_assignment[key] = row["_ts"]
            else:
                latest_ts_for_assignment[key] = max(
                    latest_ts_for_assignment[key], row["_ts"]
                )

    latest_ts_for_title = {}
    for row in emails:
        eid = row["_effective_id"]
        t = row["메일제목"].strip()
        if eid and not row["_week"]:
            key = (eid, t)
            if key not in latest_ts_for_title:
                latest_ts_for_title[key] = row["_ts"]
            else:
                latest_ts_for_title[key] = max(latest_ts_for_title[key], row["_ts"])

    # 6. Apply final row score calculation keeping duplicates as 0 points
    for row in emails:
        eid = row["_effective_id"]
        w = row["_week"]
        ts = row["_ts"]
        t = row["메일제목"].strip()

        is_duplicate = False
        if eid and w is not None:
            if ts < latest_ts_for_assignment[(eid, w)]:
                is_duplicate = True
        elif eid and not w:
            if ts < latest_ts_for_title[(eid, t)]:
                is_duplicate = True

        if is_duplicate:
            row["이유"] = "중복 (최신 메일이 아님)"
            row["점수"] = 0
            row["_final_score"] = 0
        else:
            row["점수"] = row["_row_score"]
            row["_final_score"] = row["_row_score"]
            reasons = []
            if row["_ff_score"] > 0:
                reasons.append("FirstFinder(+1)")
            if row["_format_score"] > 0:
                reasons.append("제목양식(+1)")
            if row["_deadline_score"] > 0:
                reasons.append("기한내(+1)")

            if reasons:
                row["이유"] = " ".join(reasons)

    # Calculate total per student
    total_scores = {}
    for row in emails:
        eid = row["_effective_id"]
        if eid:
            total_scores[eid] = total_scores.get(eid, 0) + row["_final_score"]

    # Clean up and export
    out_fields = fieldnames
    if "최종점수합계" not in out_fields:
        out_fields.append("최종점수합계")

    for row in emails:
        eid = row["_effective_id"]
        if eid:
            row["최종점수합계"] = total_scores[eid]
        else:
            row["최종점수합계"] = ""

        # exclude internal keys
        for k in [
            "_effective_id",
            "_ts",
            "_dt",
            "_week",
            "_format_score",
            "_deadline_score",
            "_ff_score",
            "_row_score",
            "_final_score",
        ]:
            row.pop(k, None)

    with open("output/scored_all_emails.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(emails)

    print(f"Succeessfully processed {len(emails)} emails.")
    print("Saved to output/scored_all_emails.csv")


if __name__ == "__main__":
    main()
