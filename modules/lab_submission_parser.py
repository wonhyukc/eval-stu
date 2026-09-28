import csv
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_korean_timestamp(ts_str: str) -> Optional[datetime]:
    """구글 폼 한국어 타임스탬프 문자열 파싱 (예: 2026. 9. 24 오후 4:08:02)"""
    if not ts_str:
        return None
    m = re.match(
        r"(\d+)\.\s*(\d+)\.\s*(\d+)\s*(오전|오후)\s*(\d+):(\d+):(\d+)",
        str(ts_str).strip(),
    )
    if not m:
        return None
    year, month, day, ampm, hour_s, min_s, sec_s = m.groups()
    hour = int(hour_s)
    if ampm == "오후" and hour < 12:
        hour += 12
    elif ampm == "오전" and hour == 12:
        hour = 0
    return datetime(int(year), int(month), int(day), hour, int(min_s), int(sec_s))


def get_course_deadline(
    course: str, week: str, base_dir: str = "."
) -> Optional[datetime]:
    """5input/deadline.csv 및 강좌별 수업 시작 시각을 기준으로 실습 과제 마감 일시를 계산합니다."""
    deadline_csv = os.path.join(base_dir, "5input", "deadline.csv")
    if not os.path.exists(deadline_csv):
        return None

    # 분반별 수업 시작 시각 (마감 시각)
    course_times = {
        "py": "09:00",
        "web2": "13:00",
        "web": "13:00",
        "web1": "16:00",
    }
    time_str = course_times.get(course, "09:00")

    date_str = ""
    with open(deadline_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get("week", "")).strip() == str(week).strip():
                date_str = str(row.get("lab-deadline", "")).strip()
                break

    if not date_str:
        return None

    # date_str: e.g. "9/28"
    parts = date_str.split("/")
    if len(parts) != 2:
        return None
    month, day = int(parts[0]), int(parts[1])
    h, m = [int(x) for x in time_str.split(":")]
    # 연도는 현재 연도(2026) 기준
    return datetime(2026, month, day, h, m, 0)


def deduplicate_submissions(
    rows: List[List[Any]],
    roster_students: List[Dict[str, Any]],
    deadline: Optional[datetime] = None,
    week_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """실습(Lab) 과제 1인 1건 유효 제출본 판정 (Resubmission & Deduplication Policy).

    규칙 (SSOT: 1docs/score-lab.md):
    1. 마감 전 제출 이력이 있는 경우: 마감 시각 전 가장 마지막(최신) 제출본 유효 (On-time)
    2. 마감 후에만 제출한 경우: 마감 후 제출물 중 가장 마지막(최신) 제출본 유효 (Late)
    3. (주차, 학생) 단위로 오직 1건의 유효 제출본만 추출
    """
    roster_map_last3 = {str(s.get("학번", "")).strip()[-3:]: s for s in roster_students}
    roster_map_full = {str(s.get("학번", "")).strip(): s for s in roster_students}

    # (week, student_id) 그룹화
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}

    for idx, r in enumerate(rows, start=1):
        if len(r) < 4:
            continue
        ts_str = str(r[0]).strip()
        last3 = str(r[2]).strip() if len(r) > 2 else ""
        url = str(r[3]).strip() if len(r) > 3 else ""
        commit_hash = str(r[4]).strip() if len(r) > 4 else ""
        week = str(r[5]).strip() if len(r) > 5 else ""

        if not url:
            continue

        week_clean = str(int(week)) if week.isdigit() else week
        if week_filter and week_clean != str(
            int(week_filter) if week_filter.isdigit() else week_filter
        ):
            continue

        # 학생 식별
        student_match = None
        if last3 in roster_map_full:
            student_match = roster_map_full[last3]
        elif len(last3) == 3 and last3 in roster_map_last3:
            student_match = roster_map_last3[last3]

        if not student_match:
            continue

        s_id = str(student_match.get("학번", "")).strip()
        dt = parse_korean_timestamp(ts_str)

        is_before = True
        if deadline and dt:
            is_before = dt < deadline

        key = (week_clean, s_id)
        if key not in grouped:
            grouped[key] = []

        grouped[key].append(
            {
                "row_idx": idx,
                "raw": r,
                "raw_ts": ts_str,
                "dt": dt,
                "url": url,
                "commit": commit_hash,
                "is_before_deadline": is_before,
                "student_info": student_match,
            }
        )

    valid_list: List[Dict[str, Any]] = []

    for (w, s_id), subs in grouped.items():
        before = [s for s in subs if s["is_before_deadline"]]
        after = [s for s in subs if not s["is_before_deadline"]]

        if before:
            # Rule 1: 마감 전 최종본
            valid = before[-1]
            status = "On-time"
        else:
            # Rule 2: 마감 후 최종본
            valid = after[-1]
            status = "Late"

        student_info = valid["student_info"]
        valid_list.append(
            {
                "week": int(w) if w.isdigit() else 99,
                "student_id": s_id,
                "student_name": student_info.get("성명", "")
                or student_info.get("한국어이름", ""),
                "status": status,
                "total_attempts": len(subs),
                "timestamp": valid["raw_ts"],
                "datetime": valid["dt"],
                "url": valid["url"],
                "commit": valid["commit"],
                "raw_row": valid["raw"],
            }
        )

    # 정렬: 주차 오름차순 -> 학번 오름차순
    valid_list.sort(key=lambda x: (x["week"], x["student_id"]))
    return valid_list
