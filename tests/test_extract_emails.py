import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from bin.extract_emails import get_time_window, parse_students


def test_get_time_window():
    # 인자 없이 호출 시 폴백: start < deadline < grace, 간격 7일 이내
    start_dt, deadline_dt, grace_dt = get_time_window()
    assert start_dt < deadline_dt < grace_dt
    assert grace_dt == deadline_dt + timedelta(minutes=15)

    # 주차 지정 시 deadline.csv에서 읽어야 함
    start_dt4, deadline_dt4, grace_dt4 = get_time_window("4")
    assert start_dt4 < deadline_dt4 < grace_dt4
    # 4주차 email deadline = 9/25 0:00, grace = 9/25 0:15
    assert deadline_dt4.month == 9
    assert deadline_dt4.day == 25
    assert grace_dt4.minute == 15


def test_parse_students():
    # 파일이 존재하는 환경에서 실행될 경우 딕셔너리 반환 확인
    name_to_id, id_to_track, id_to_names = parse_students()

    assert isinstance(name_to_id, dict)
    assert isinstance(id_to_track, dict)

    # 만약 데이터가 파싱되었다면, key와 value가 모두 문자열이어야 함
    if len(id_to_track) > 0:
        for k, v in id_to_track.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
            assert k.isdigit()  # 학번은 숫자 형태
            assert v in {"1", "2", "4"}  # 트랙 번호는 1, 2, 4 로 정규화됨


def test_build_reply_body():
    from bin.extract_emails import build_reply_body

    id_to_names = {
        "2026300742": {"eng": "John Doe", "kor": "홍길동"},
        "2026300123": {"eng": "Jane Smith", "kor": "김철수"},
    }

    # K트랙 (4반) 테스트 -> 100% 한글
    row_py = {
        "학번": "2026300742",
        "track": "4",
        "점수": 1.0,
        "이유": "정상 제출 (기한내/정확한 양식)",
        "이름": "홍길동",
    }
    body_py = build_reply_body(row_py, "0.5", id_to_names)
    assert "안녕하세요 홍길동 학생" in body_py
    assert "0.5 과제 이메일이 정상적으로 접수 및 채점되었습니다" in body_py
    assert "정원혁 드림" in body_py

    # E트랙 (1반/2반) 테스트 -> 100% 영문
    row_web = {
        "학번": "2026300123",
        "track": "1",
        "점수": 1.0,
        "이유": "On-time & Exact Format",
        "이름": "Jane Smith",
    }
    body_web = build_reply_body(row_web, "0.5", id_to_names)
    assert "Dear Jane Smith" in body_web
    assert (
        "Your assignment submission has been received and graded successfully"
        in body_web
    )
    assert "Wonhyuk William Chung" in body_web


def test_print_grading_summary(capsys):
    from bin.extract_emails import print_grading_summary

    rows = [
        {"track": "4", "점수": 1.0, "is_replied": True},
        {"track": "1", "점수": 0.9, "is_replied": False},
        {"track": "2", "점수": 0.0, "is_replied": True},
    ]
    reply_stats = {
        "already_replied": 2,
        "newly_replied": 1,
        "unreplied": 0,
        "total_replied": 3,
        "total_submissions": 3,
    }
    print_grading_summary(rows, reply_stats=reply_stats)
    captured = capsys.readouterr().out
    assert "📊 [채점 결과 요약]" in captured
    assert "✉️ [답장 현황]" in captured
    assert "총 답장 건수   : 3건" in captured
    assert "이미 답장 완료 : 2건" in captured
    assert "이번에 답장 완료: 1건" in captured


@pytest.fixture
def interactive_grader(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, mock_open
    from bin import extract_emails as engine
    from modules.email_submission import select_original_submission

    case = SimpleNamespace(messages=[], track="1", feedback=[])
    page = MagicMock()
    row = page.locator.return_value.nth.return_value
    subject = MagicMock()
    subject.count.return_value = 1
    subject.inner_text.return_value = "Assignment 0.5 2026000123"
    empty = MagicMock()
    empty.count.return_value = 0
    row.locator.side_effect = lambda selector: (
        subject if selector == "span.bog" else empty
    )
    row.inner_html.return_value = ""
    case.rows = [row]
    case.threads = None
    page.locator.return_value.count.side_effect = lambda: len(case.rows)
    page.locator.return_value.nth.side_effect = lambda index: case.rows[index]
    playwright = MagicMock()
    context = (
        playwright.__enter__.return_value.chromium.launch_persistent_context.return_value
    )
    context.pages = [page]
    monkeypatch.setattr(engine, "sync_playwright", lambda: playwright)
    monkeypatch.setattr(
        engine,
        "parse_students",
        lambda: (
            {"student@example.test": "2026000123"},
            {"2026000123": case.track},
            {},
        ),
    )
    deadline = datetime(2026, 10, 1, 23, 59, tzinfo=engine.KST)
    grace = datetime(2026, 10, 2, 0, 15, tzinfo=engine.KST)
    monkeypatch.setattr(
        engine,
        "get_time_window",
        lambda *args: (deadline - timedelta(days=7), deadline, grace),
    )
    monkeypatch.setattr(
        engine,
        "read_original_submission",
        lambda page, source_row, grace_deadline=None, start_time=None: select_original_submission(
            (
                case.messages
                if case.threads is None
                else case.threads[case.rows.index(source_row)]
            ),
            grace_deadline,
            start_time,
        ),
    )
    monkeypatch.setattr(engine, "print_grading_summary", MagicMock())
    monkeypatch.setattr(engine.os, "makedirs", MagicMock())
    monkeypatch.setattr("builtins.open", mock_open())
    writer = MagicMock()
    monkeypatch.setattr(engine.csv, "DictWriter", lambda *args, **kwargs: writer)

    def reply(page, item, task_id, names):
        case.feedback.append(engine.build_reply_body(item, task_id, names))
        return True

    monkeypatch.setattr(engine, "send_single_reply", reply)
    case.upload = MagicMock()
    monkeypatch.setattr(engine, "_upload_rows_to_sheet", case.upload)
    case.engine, case.writer, case.context, case.row = engine, writer, context, row
    return case


@pytest.mark.parametrize("student_filter", [None, "123"])
@pytest.mark.parametrize(
    "stamps,bodies,expected_date,expected_score",
    [
        (
            ["Thu, 1 Oct 2026 09:00:00 +0900", "Thu, 1 Oct 2026 22:00:00 +0900"],
            ["https://example.test/old", ""],
            "10/01 22:00",
            0.0,
        ),
        (
            ["Fri, 2 Oct 2026 10:00:00 +0900", "Thu, 1 Oct 2026 22:00:00 +0900"],
            ["https://example.test/late", "https://example.test/on-time"],
            "10/01 22:00",
            1.0,
        ),
        (
            ["Fri, 2 Oct 2026 10:00:00 +0900", "Sat, 3 Oct 2026 09:00:00 +0900"],
            ["https://example.test/late", ""],
            "10/03 09:00",
            0.0,
        ),
    ],
)
def test_interactive_selects_submission_across_all_threads(
    interactive_grader, student_filter, stamps, bodies, expected_date, expected_score
):
    from unittest.mock import MagicMock

    case = interactive_grader
    case.rows = []
    case.threads = []
    for stamp, body in zip(stamps, bodies):
        row = MagicMock()
        subject = MagicMock()
        subject.count.return_value = 1
        subject.inner_text.return_value = "Assignment 0.5 2026000123"
        empty = MagicMock()
        empty.count.return_value = 0
        row.locator.side_effect = lambda selector, sub=subject, none=empty: (
            sub if selector == "span.bog" else none
        )
        row.inner_html.return_value = ""
        case.rows.append(row)
        case.threads.append(
            [
                {
                    "sender_email": "student@example.test",
                    "sender_name": "Student",
                    "date_str": stamp,
                    "body_html": body,
                }
            ]
        )

    case.engine.extract_gmail_interactive(
        target_week="5", target_id=student_filter, do_sync=True
    )

    saved = case.writer.writerows.call_args.args[0]
    assert len(saved) == 1
    assert saved[0]["점수"] == expected_score
    assert saved[0]["날짜"] == expected_date
    assert len(case.upload.call_args.args[0]) == 1


def test_interactive_selects_latest_before_deadline_inside_thread(interactive_grader):
    case = interactive_grader
    case.messages = [
        {
            "sender_email": "student@example.test",
            "sender_name": "Student",
            "date_str": "Thu, 1 Oct 2026 09:00:00 +0900",
            "body_html": "https://example.test/old",
        },
        {
            "sender_email": "student@example.test",
            "sender_name": "Student",
            "date_str": "Thu, 1 Oct 2026 22:00:00 +0900",
            "body_html": "",
        },
        {
            "sender_email": "student@example.test",
            "sender_name": "Student",
            "date_str": "Fri, 2 Oct 2026 10:00:00 +0900",
            "body_html": "https://example.test/late",
        },
    ]
    case.engine.extract_gmail_interactive(target_week="5")
    saved = case.writer.writerows.call_args.args[0]
    assert len(saved) == 1
    assert saved[0]["점수"] == 0.0
    assert saved[0]["날짜"] == "10/01 22:00"


def test_single_reply_visits_selected_submission_thread():
    from unittest.mock import MagicMock
    from bin.extract_emails import send_single_reply

    page = MagicMock()
    instructor = MagicMock()
    instructor.count.return_value = 0
    reply_button = MagicMock()
    reply_button.count.return_value = 1
    textbox = MagicMock()
    textbox.count.return_value = 1

    def locate(selector):
        if selector == "span.gD":
            return instructor
        if selector.startswith('span[role="link"]'):
            return reply_button
        if selector.startswith('div[role="textbox"]'):
            return textbox
        raise AssertionError("선택한 스레드 대신 검색 목록을 조회했습니다.")

    page.locator.side_effect = locate
    selected_url = "https://mail.google.com/mail/u/0/#search/fake/selected-thread"
    item = {
        "학번": "2026000123",
        "track": "1",
        "점수": 0.7,
        "이유": "Missing Student ID or 0.x in Subject",
        "thread_url": selected_url,
    }
    assert send_single_reply(page, item, "0.5", {}) is True
    page.goto.assert_called_once_with(
        selected_url, wait_until="domcontentloaded", timeout=30000
    )
    assert "0.7" in textbox.first.fill.call_args.args[0]


@pytest.mark.parametrize(
    "student_date,expected_score",
    [
        ("Thu, 1 Oct 2026 23:50:00 +0900", 1.0),
        ("Fri, 2 Oct 2026 10:00:00 +0900", 0.5),
        ("Mon, 5 Oct 2026 16:00:00 +0900", 0.0),
        ("", None),
    ],
)
@pytest.mark.parametrize(
    "reply_date",
    ["Thu, 1 Oct 2026 23:55:00 +0900", "Tue, 6 Oct 2026 18:00:00 +0900"],
)
def test_interactive_grading_uses_student_timestamp(
    interactive_grader, student_date, expected_score, reply_date
):
    """기본 진입점의 채점·저장 날짜가 교수 답장 날짜와 무관하다."""
    from modules.email_submission import (
        OriginalSubmissionError,
        select_original_submission,
    )

    case = interactive_grader
    case.messages = [
        {
            "sender_email": "student@example.test",
            "sender_name": "Student",
            "date_str": student_date,
            "body_html": "https://example.test/submission",
        },
        {
            "sender_email": "wonhyukc@stu.ac.kr",
            "sender_name": "Professor",
            "date_str": reply_date,
        },
    ]
    if expected_score is None:
        with pytest.raises(OriginalSubmissionError):
            case.engine.extract_gmail_interactive(target_week="5", skip_sheet=True)
        case.writer.writerows.assert_not_called()
        case.context.close.assert_called_once()
        return

    case.engine.extract_gmail_interactive(target_week="5", skip_sheet=True)

    saved = case.writer.writerows.call_args.args[0]
    assert len(saved) == 1
    assert saved[0]["점수"] == expected_score
    assert saved[0]["날짜"] == select_original_submission(case.messages)[
        "sent_at"
    ].strftime("%m/%d %H:%M")
    assert saved[0]["is_replied"] is True
    assert all(call.args[0] != "td.xW span" for call in case.row.locator.call_args_list)


def test_original_submission_excludes_instructor_and_never_uses_reply_date():
    from modules.email_submission import select_original_submission

    messages = [
        {
            "sender_email": "wonhyukc@stu.ac.kr",
            "date_str": "Tue, 6 Oct 2026 18:00:00 +0900",
        },
        {
            "sender_email": "student@example.test",
            "sender_name": "Student",
            "date_str": "Thu, 1 Oct 2026 23:50:00 +0900",
        },
    ]
    submission = select_original_submission(messages)
    assert submission["sender_email"] == "student@example.test"
    assert submission["sent_at"] == datetime(
        2026, 10, 1, 23, 50, tzinfo=timezone(timedelta(hours=9))
    )
    assert submission["is_replied"]
    assert select_original_submission(messages[:1]) is None


@pytest.mark.parametrize("track", ["1", "4"])
@pytest.mark.parametrize(
    "body_html,expected_score",
    [
        ("", 0.0),
        (" &nbsp; \n ", 0.0),
        ("&gt; https://example.test/old", 0.0),
        (
            '<div class="gmail_quote"><p>'
            + "가" * 40
            + "</p>https://example.test/old</div>",
            0.0,
        ),
        ("감사합니다<blockquote>https://example.test/old</blockquote>", 0.0),
        ("짧은 본문\nOn Thu, Professor wrote:\nhttps://example.test/old", 0.0),
        ("가 " * 29, 0.0),
        ("가 " * 30, 1.0),
        ("https://example.test/x", 1.0),
        ('<a href="https://example.test/x">제출 링크</a>', 1.0),
        ("https://", 0.0),
    ],
)
def test_interactive_body_validation_and_feedback(
    interactive_grader, track, body_html, expected_score
):
    case = interactive_grader
    case.track = track
    case.messages = [
        {
            "sender_email": "student@example.test",
            "sender_name": "Student",
            "date_str": "Thu, 1 Oct 2026 23:50:00 +0900",
            "body_html": body_html,
        }
    ]

    case.engine.extract_gmail_interactive(target_week="5", do_reply=True, do_sync=True)

    saved = case.writer.writerows.call_args.args[0]
    assert len(saved) == 1
    assert saved[0]["점수"] == expected_score
    assert saved[0]["유형"] == "0.5"
    assert saved[0]["날짜"] == "10/01 23:50"
    assert case.upload.call_args.args[0][0][3] == expected_score
    assert len(case.feedback) == 1
    if expected_score == 0.0:
        assert saved[0]["이유"] == (
            "Empty Body / Quoted Text Only"
            if track == "1"
            else "본문 미작성(단순 회신)"
        )
        assert "successfully" not in case.feedback[0]
        assert "정상적으로 접수" not in case.feedback[0]
    else:
        assert (
            "successfully" in case.feedback[0] or "정상적으로 접수" in case.feedback[0]
        )


@pytest.mark.parametrize("bad_date", ["", "invalid", "Oct 1, 2026"])
def test_original_submission_requires_own_timestamp(bad_date):
    from modules.email_submission import (
        OriginalSubmissionError,
        select_original_submission,
    )

    with pytest.raises(OriginalSubmissionError, match="원본 발송 시각"):
        select_original_submission(
            [
                {"sender_email": "student@example.test", "date_str": bad_date},
                {
                    "sender_email": "wonhyukc@stu.ac.kr",
                    "date_str": "Tue, 6 Oct 2026 18:00:00 +0900",
                },
            ]
        )


@pytest.mark.parametrize(
    "student_date,restore_fails,body_available",
    [
        ("Thu, 1 Oct 2026 23:50:00 +0900", False, True),
        ("", False, True),
        ("Thu, 1 Oct 2026 23:50:00 +0900", True, True),
        ("Thu, 1 Oct 2026 23:50:00 +0900", False, False),
    ],
)
def test_read_original_submission_restores_search_page(
    student_date, restore_fails, body_available
):
    from unittest.mock import MagicMock
    from bin.extract_emails import read_original_submission
    from modules.email_submission import OriginalSubmissionError

    page = MagicMock()
    page.url = "https://mail.google.com/mail/u/0/#search/fake"
    if restore_fails:
        page.goto.side_effect = RuntimeError("검색 목록 복귀 실패")
    row = MagicMock()
    elements = []
    bodies = []
    for address, name, stamp in [
        ("student@example.test", "Student", student_date),
        ("wonhyukc@stu.ac.kr", "Professor", "Tue, 6 Oct 2026 18:00:00 +0900"),
    ]:
        sender = MagicMock()
        sender.count.return_value = 1
        sender.first.get_attribute.side_effect = {"email": address, "name": name}.get
        date = MagicMock()
        date.count.return_value = 1
        date.first.get_attribute.return_value = stamp
        date.first.inner_text.return_value = stamp
        body = MagicMock()
        body.first.inner_html.return_value = "https://example.test/student"
        if not body_available:
            body.first.wait_for.side_effect = RuntimeError("본문 렌더링 실패")
        bodies.append(body)
        element = MagicMock()
        element.locator.side_effect = {
            "span.gD[email], span.g2[email]": sender,
            "span.g3": date,
            "div.a3s.aiL": body,
        }.get
        elements.append(element)
    messages = MagicMock()
    messages.count.return_value = len(elements)
    messages.nth.side_effect = elements.__getitem__
    expand = MagicMock()
    expand.count.return_value = 1
    page.locator.side_effect = lambda selector: (
        messages if selector == "div.adn.ads" else expand
    )

    if student_date and not restore_fails and body_available:
        result = read_original_submission(page, row)
        assert result["date_str"] == student_date
        assert result["is_replied"] is True
        assert result["body_html"] == "https://example.test/student"
    else:
        with pytest.raises(OriginalSubmissionError):
            read_original_submission(page, row)

    row.click.assert_called_once()
    expand.first.click.assert_called_once()
    page.goto.assert_called_once_with(page.url, wait_until="domcontentloaded")
    if not restore_fails:
        page.wait_for_selector.assert_any_call("tr.zA", timeout=10000)
    bodies[0].first.wait_for.assert_called_once()
    bodies[1].first.inner_html.assert_not_called()
