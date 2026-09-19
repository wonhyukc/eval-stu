import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import normalize_row_to_11cols, route_web_rows
from modules.grader import grade_assignment


def test_normalize_row_to_11cols_from_9cols():
    # 구 9열 구조: [no, sid, track, score, type, reason, date, name, subject]
    old_row = [
        1,
        "2026300123",
        "15144",
        1.0,
        "0.2",
        "On-time & Exact Format",
        "2026-09-15",
        "John Doe",
        "과제 0.2 2026300123",
    ]
    new_row = normalize_row_to_11cols(old_row)
    assert len(new_row) == 11
    # [No, wk, ID, Track, Score, Type1, Type2, Reason, Date, Name, Subject]
    assert new_row[0] == 1  # No
    assert new_row[1] == "2"  # wk (0.2에서 추출)
    assert new_row[2] == "2026300123"  # ID
    assert new_row[3] == "15144"  # Track
    assert new_row[4] == 1.0  # Score
    assert new_row[5] == "hw"  # Type1
    assert new_row[6] == "0.2"  # Type2
    assert new_row[7] == "On-time & Exact Format"  # Reason
    assert new_row[8] == "2026-09-15"  # Date
    assert new_row[9] == "John Doe"  # Name
    assert new_row[10] == "과제 0.2 2026300123"  # Subject


def test_normalize_row_to_11cols_already_11cols():
    row_11 = [
        1,
        "1",
        "2026300999",
        "15143",
        1.0,
        "hw",
        "0.1",
        "Pass",
        "2026-09-10",
        "Alice",
        "Subject",
    ]
    result = normalize_row_to_11cols(row_11)
    assert result == row_11


def test_route_web_rows_11cols():
    # 11열 구조: Track은 인덱스 3
    web1_row = [
        1,
        "1",
        "2026300111",
        "15143",
        1.0,
        "hw",
        "0.1",
        "Pass",
        "2026-09-10",
        "Alice",
        "Subj1",
    ]
    web2_row = [
        2,
        "1",
        "2026300222",
        "15144",
        1.0,
        "hw",
        "0.1",
        "Pass",
        "2026-09-10",
        "Bob",
        "Subj2",
    ]

    r1, r2 = route_web_rows([web1_row, web2_row])
    assert len(r1) == 1
    assert r1[0][2] == "2026300111"
    assert len(r2) == 1
    assert r2[0][2] == "2026300222"


def test_grade_assignment_type_fields():
    email_data = {
        "subject": "과제 0.4 2026300123",
        "date_str": "Fri, 18 Sep 2026 12:00:00 +0900",
        "is_replied_by_instructor": False,
    }
    res = grade_assignment(email_data, "0.4")
    assert res["type1"] == "hw"
    assert res["type2"] == "0.4"
