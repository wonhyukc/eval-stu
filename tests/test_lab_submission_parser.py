import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.lab_submission_parser import (
    parse_korean_timestamp,
    parse_english_timestamp,
    parse_timestamp,
    deduplicate_submissions,
)


def test_parse_korean_timestamp():
    # 오전
    dt1 = parse_korean_timestamp("2026. 9. 24 오전 11:09:35")
    assert dt1 == datetime(2026, 9, 24, 11, 9, 35)

    # 오후
    dt2 = parse_korean_timestamp("2026. 9. 24 오후 4:08:02")
    assert dt2 == datetime(2026, 9, 24, 16, 8, 2)

    # 오전 12시 (자정 00시)
    dt3 = parse_korean_timestamp("2026. 9. 24 오전 12:30:00")
    assert dt3 == datetime(2026, 9, 24, 0, 30, 0)

    # 오후 12시 (정오 12시)
    dt4 = parse_korean_timestamp("2026. 9. 24 오후 12:30:00")
    assert dt4 == datetime(2026, 9, 24, 12, 30, 0)

    # 잘못된 형식
    assert parse_korean_timestamp("") is None
    assert parse_korean_timestamp("invalid") is None


def test_deduplicate_submissions_single_on_time():
    roster = [{"학번": "2026300857", "성명": "NGUYEN"}]
    deadline = datetime(2026, 9, 21, 9, 0, 0)
    rows = [
        ["2026. 9. 15 오전 10:00:00", "a@a.com", "857", "https://url1", "", "3", "04"]
    ]
    res = deduplicate_submissions(rows, roster, deadline)
    assert len(res) == 1
    assert res[0]["student_id"] == "2026300857"
    assert res[0]["status"] == "On-time"
    assert res[0]["url"] == "https://url1"
    assert res[0]["total_attempts"] == 1


def test_deduplicate_submissions_multiple_before_deadline():
    """마감 전 여러 번 제출한 경우 가장 최근(최신) 제출본 유효"""
    roster = [{"학번": "2026300869", "성명": "MIN"}]
    deadline = datetime(2026, 9, 21, 9, 0, 0)
    rows = [
        ["2026. 9. 14 오전 11:12:38", "a@a.com", "869", "https://first", "", "3", "04"],
        [
            "2026. 9. 14 오전 11:32:21",
            "a@a.com",
            "869",
            "https://second",
            "",
            "3",
            "04",
        ],
        ["2026. 9. 17 오후 1:02:45", "a@a.com", "869", "https://latest", "", "3", "04"],
    ]
    res = deduplicate_submissions(rows, roster, deadline)
    assert len(res) == 1
    assert res[0]["student_id"] == "2026300869"
    assert res[0]["status"] == "On-time"
    assert res[0]["url"] == "https://latest"
    assert res[0]["total_attempts"] == 3


def test_deduplicate_submissions_before_and_after_deadline():
    """마감 전과 마감 후 모두 제출한 경우, 마감 전 최신 제출본 유효 (마감 후 무시)"""
    roster = [{"학번": "2026300866", "성명": "SHOON"}]
    deadline = datetime(2026, 9, 21, 9, 0, 0)
    rows = [
        [
            "2026. 9. 17 오후 7:13:22",
            "a@a.com",
            "866",
            "https://on_time",
            "",
            "3",
            "04",
        ],
        [
            "2026. 9. 22 오후 10:00:00",
            "a@a.com",
            "866",
            "https://after_dl",
            "",
            "3",
            "04",
        ],
    ]
    res = deduplicate_submissions(rows, roster, deadline)
    assert len(res) == 1
    assert res[0]["status"] == "On-time"
    assert res[0]["url"] == "https://on_time"
    assert res[0]["total_attempts"] == 2


def test_deduplicate_submissions_only_after_deadline():
    """마감 후에만 제출한 경우 마감 후 최신 제출본 유효 (지각)"""
    roster = [{"학번": "2026300861", "성명": "SON"}]
    deadline = datetime(2026, 9, 28, 9, 0, 0)
    rows = [
        ["2026. 9. 28 오전 10:30:00", "a@a.com", "861", "https://late1", "", "4", "04"],
        [
            "2026. 9. 28 오전 10:41:07",
            "a@a.com",
            "861",
            "https://late_latest",
            "",
            "4",
            "04",
        ],
    ]
    res = deduplicate_submissions(rows, roster, deadline)
    assert len(res) == 1
    assert res[0]["status"] == "Late"
    assert res[0]["url"] == "https://late_latest"
    assert res[0]["total_attempts"] == 2


def test_parse_english_timestamp():
    dt1 = parse_english_timestamp("Sep 24, 2026, 4:08:02 PM")
    assert dt1 == datetime(2026, 9, 24, 16, 8, 2)

    dt2 = parse_english_timestamp("September 24, 2026 4:08:02 PM")
    assert dt2 == datetime(2026, 9, 24, 16, 8, 2)

    dt3 = parse_english_timestamp("Sep 24, 2026, 12:30:00 AM")
    assert dt3 == datetime(2026, 9, 24, 0, 30, 0)

    assert parse_english_timestamp("") is None
    assert parse_english_timestamp("invalid") is None


def test_parse_timestamp_both_formats():
    assert parse_timestamp("2026. 9. 24 오후 4:08:02") == datetime(
        2026, 9, 24, 16, 8, 2
    )
    assert parse_timestamp("Sep 24, 2026, 4:08:02 PM") == datetime(
        2026, 9, 24, 16, 8, 2
    )


def test_deduplicate_submissions_reverse_sorted():
    """입력이 역순으로 되어있어도 timestamp 기준으로 최신을 가져오는지 확인"""
    roster = [{"학번": "2026300869", "성명": "MIN"}]
    deadline = datetime(2026, 9, 21, 9, 0, 0)
    rows = [
        ["2026. 9. 17 오후 1:02:45", "a@a.com", "869", "https://latest", "", "3", "04"],
        [
            "2026. 9. 14 오전 11:32:21",
            "a@a.com",
            "869",
            "https://second",
            "",
            "3",
            "04",
        ],
        ["2026. 9. 14 오전 11:12:38", "a@a.com", "869", "https://first", "", "3", "04"],
    ]
    res = deduplicate_submissions(rows, roster, deadline)
    assert len(res) == 1
    assert res[0]["status"] == "On-time"
    assert res[0]["url"] == "https://latest"
    assert res[0]["total_attempts"] == 3


def test_deduplicate_submissions_unparseable_date_with_deadline():
    """파싱 불가능한 날짜는 deadline이 있으면 Late로 간주"""
    roster = [{"학번": "2026300861", "성명": "SON"}]
    deadline = datetime(2026, 9, 28, 9, 0, 0)
    rows = [
        ["invalid_date_format", "a@a.com", "861", "https://invalid", "", "4", "04"],
    ]
    res = deduplicate_submissions(rows, roster, deadline)
    assert len(res) == 1
    assert res[0]["status"] == "Late"
