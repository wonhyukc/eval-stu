from datetime import datetime

import pytest

from modules.email_submission import (
    KST,
    OriginalSubmissionError,
    parse_submission_datetime,
    select_original_submission,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Thu, Oct 1, 2026, 10:55 PM", (2026, 10, 1, 22, 55, 0)),
        ("Oct 1, 2026, 12:00 AM", (2026, 10, 1, 0, 0, 0)),
        ("October 1, 2026, 12:30 PM", (2026, 10, 1, 12, 30, 0)),
        ("Oct 1, 2026, 1:05:10 PM", (2026, 10, 1, 13, 5, 10)),
        ("2026년 10월 1일 (목) 오전 12:30", (2026, 10, 1, 0, 30, 0)),
        ("2026년 10월 1일 (목) 오후 12:30", (2026, 10, 1, 12, 30, 0)),
        ("2026년 10월 1일 (목) 오후 1:05:20", (2026, 10, 1, 13, 5, 20)),
        ("Thu, 1 Oct 2026 16:05:00 +0000", (2026, 10, 2, 1, 5, 0)),
        ("Thu, 1 Oct 2026 16:05:00 +0900", (2026, 10, 1, 16, 5, 0)),
        ("Thu, 1 Oct 2026 16:05:00", (2026, 10, 1, 16, 5, 0)),
    ],
)
def test_parse_original_timestamp(raw, expected):
    assert parse_submission_datetime(raw) == datetime(*expected, tzinfo=KST)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "bad",
        "Oct 1, 2026",
        "2026년 2월 30일 오전 9:00",
        "2026년 10월 1일 오후 27:00",
    ],
)
def test_invalid_original_timestamp_is_not_invented(raw):
    assert parse_submission_datetime(raw) is None


def test_original_message_requires_sender_identity():
    with pytest.raises(OriginalSubmissionError, match="발신자"):
        select_original_submission(
            [{"sender_email": "", "date_str": "Thu, 1 Oct 2026 16:05:00 +0900"}]
        )


def test_no_messages_are_not_a_submission():
    assert select_original_submission([]) is None


@pytest.mark.parametrize(
    "timestamps,expected_index",
    [
        (["10/01 09:00", "10/01 22:00"], 1),
        (["10/02 10:00", "10/01 22:00"], 1),
        (["10/02 10:00", "10/03 09:00"], 1),
        (["10/03 09:00", "10/02 10:00"], 0),
        (["10/02 00:15", "10/02 00:16"], 1),
        (["10/02 00:14", "10/02 00:15"], 0),
    ],
)
def test_original_submission_selects_latest_with_grace_priority(
    timestamps, expected_index
):
    grace = datetime(2026, 10, 2, 0, 15, tzinfo=KST)
    messages = [
        {
            "sender_email": "student@example.test",
            "date_str": datetime.strptime("2026/" + stamp, "%Y/%m/%d %H:%M")
            .replace(tzinfo=KST)
            .strftime("%a, %d %b %Y %H:%M:%S %z"),
            "body_html": f"submission {index}",
        }
        for index, stamp in enumerate(timestamps)
    ]
    result = select_original_submission(messages, grace)
    assert result["body_html"] == f"submission {expected_index}"
    assert messages[expected_index].get("sent_at") is None


def test_duplicate_records_keep_week_and_student_separate():
    from modules.email_submission import deduplicate_submissions

    grace = datetime(2026, 10, 2, 0, 15, tzinfo=KST)
    records = [
        {
            "student_id": "123",
            "task_id": "0.5",
            "sent_at": datetime(2026, 10, 1, 9, tzinfo=KST),
            "score": 1.0,
        },
        {
            "student_id": "123",
            "task_id": "0.5",
            "sent_at": datetime(2026, 10, 1, 22, tzinfo=KST),
            "score": 0.7,
        },
        {
            "student_id": "123",
            "task_id": "0.6",
            "sent_at": datetime(2026, 10, 1, 22, tzinfo=KST),
            "score": 1.0,
        },
        {
            "student_id": "456",
            "task_id": "0.5",
            "sent_at": datetime(2026, 10, 1, 22, tzinfo=KST),
            "score": 0.9,
        },
    ]
    selected = deduplicate_submissions(records, grace)
    assert selected == records[1:]


def test_unknown_timestamp_cannot_silently_choose_an_older_submission():
    grace = datetime(2026, 10, 2, 0, 15, tzinfo=KST)
    with pytest.raises(OriginalSubmissionError, match="발송 시각"):
        select_original_submission(
            [
                {
                    "sender_email": "student@example.test",
                    "date_str": "Thu, 1 Oct 2026 09:00:00 +0900",
                },
                {"sender_email": "student@example.test", "date_str": ""},
            ],
            grace,
        )


def test_messages_before_collection_window_do_not_override_current_late_submission():
    grace = datetime(2026, 10, 2, 0, 15, tzinfo=KST)
    start = datetime(2026, 9, 28, tzinfo=KST)
    messages = [
        {
            "sender_email": "student@example.test",
            "date_str": "Thu, 10 Sep 2026 09:00:00 +0900",
            "body_html": "old semester",
        },
        {
            "sender_email": "student@example.test",
            "date_str": "Fri, 2 Oct 2026 10:00:00 +0900",
            "body_html": "current week",
        },
    ]
    assert (
        select_original_submission(messages, grace, start)["body_html"]
        == "current week"
    )


@pytest.mark.parametrize(
    "body_html,expected",
    [
        (
            "<p>학생 작성</p><blockquote><div>인용<br>https://example.test/old</div></blockquote><p>추가 작성</p>",
            "학생 작성\n\n추가 작성",
        ),
        (
            "<div class='gmail_quote extra'><div>옛 본문<img src='x'><br>인용</div></div><p>학생 작성</p>",
            "학생 작성",
        ),
        (
            "학생 작성<div class='gmail_attr'>On Thu, Professor wrote:</div><blockquote>옛 본문</blockquote>",
            "학생 작성",
        ),
        ("&gt; 옛 본문\n학생 작성", "학생 작성"),
        ("학생 작성\nOn Thu, Professor wrote:\n인용 본문", "학생 작성"),
        ("학생 작성\nSomeone đã viết:\nhttps://example.test/old", "학생 작성"),
        ("학생 작성\n교수님이 작성:\n인용 본문", "학생 작성"),
        (
            "<script>무시할 스크립트</script><style>무시할 스타일</style><p>학생 작성</p>",
            "학생 작성",
        ),
    ],
)
def test_extract_student_text_excludes_quotes(body_html, expected):
    from modules.email_submission import extract_pure_body

    assert extract_pure_body(body_html) == expected


@pytest.mark.parametrize(
    "body_html,expected",
    [
        ("", False),
        (" &nbsp; \t\n", False),
        ("가 " * 29, False),
        ("가\n" * 30, True),
        ("<b>가</b>" * 29, False),
        ("<b>가</b>" * 30, True),
        ("https://example.test/x", True),
        ("HTTP://example.test/x", True),
        ("http://[::1]/", True),
        ('<a href="https://example.test/x">링크</a>', True),
        ('<blockquote><a href="https://example.test/x">링크</a></blockquote>', False),
        ("https://", False),
        ("https://[invalid", False),
        ("https://example.test:bad", False),
        ('<a href="https://example.test/ x">링크</a>', False),
        ('<a href="javascript:alert(1)">링크</a>', False),
    ],
)
def test_validate_pure_body_length_or_url(body_html, expected):
    from modules.email_submission import has_valid_submission_body

    assert has_valid_submission_body(body_html) is expected


def test_generate_missing_submission_rows():
    from modules.email_submission import generate_missing_submission_rows

    graded_ids = {"111", "222"}
    roster = [
        {"id": "111", "track": "761", "eng_name": "Alice"},
        {"id": "333", "track": "762", "eng_name": "Bob"},
        {"student_id": "444", "track": "15143", "name": "Charlie"},
    ]

    rows_py = generate_missing_submission_rows(graded_ids, roster, "4", "py")
    assert len(rows_py) == 2

    bob_row = rows_py[0]
    assert bob_row[2] == "333"
    assert bob_row[4] == "0.00"
    assert bob_row[7] == "미제출"
    assert bob_row[9] == "Bob"

    rows_web = generate_missing_submission_rows(graded_ids, roster, "5", "web")
    charlie_row = rows_web[1]
    assert charlie_row[2] == "444"
    assert charlie_row[7] == "No submission"
    assert charlie_row[9] == "Charlie"

    # Test dictionary input
    roster_dict = {
        "111": {"id": "111", "track": "761", "eng_name": "Alice"},
        "333": {"id": "333", "track": "762", "eng_name": "Bob"},
    }
    rows_dict = generate_missing_submission_rows(graded_ids, roster_dict, "4", "py")
    assert len(rows_dict) == 1
    assert rows_dict[0][2] == "333"
