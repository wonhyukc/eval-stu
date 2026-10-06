"""외부 서비스 없이 자동 채점기의 전체 제출본 순회·선택·업로드를 검증한다."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from bin import auto_grade_email as engine

SID = "2026300123"
GRACE = datetime(2026, 10, 2, 0, 15, tzinfo=engine.KST)


def _message(stamp, body="https://example.test/submission"):
    return {"date_str": stamp, "body": body, "sender_email": "student@example.test"}


def _element(text="", **attributes):
    node = MagicMock()
    node.count.return_value = 1
    node.inner_text.return_value = text
    node.get_attribute.side_effect = attributes.get
    node.first = node
    return node


@pytest.fixture
def auto_grader(monkeypatch):
    def run(thread_pages, student_filter=None):
        state = {"page": 0, "thread": ""}
        threads = {}
        pages = []
        for thread_page in thread_pages:
            rows = []
            for item in thread_page:
                tid = f"thread{len(threads)}"
                message_nodes = []
                for message in item["messages"]:
                    sender = _element("Student", email=message["sender_email"])
                    date = _element(message["date_str"], title=message["date_str"])
                    body = _element(message["body"])
                    node = MagicMock()
                    node.locator.side_effect = {
                        "span.gD": sender,
                        "span.g3": date,
                        "div.a3s.aiL": body,
                    }.get
                    message_nodes.append(node)
                threads[tid] = message_nodes
                row = MagicMock()
                row.get_attribute.side_effect = {"data-legacy-thread-id": tid}.get
                row.locator.side_effect = {
                    "span.bog": _element(item["subject"]),
                    "div.yW span[name]": _element("Student", name="Student"),
                    "td.xW span": _element(
                        "Professor reply date", title="Professor reply date"
                    ),
                }.get
                rows.append(row)
            pages.append(rows)

        page = MagicMock()
        page.url = "https://mail.google.com/mail/u/0/"

        def navigate(url):
            page.url = url
            tid = url.rsplit("/", 1)[-1]
            if tid in threads:
                state["thread"] = tid

        page.goto.side_effect = navigate
        rows = MagicMock()
        rows.count.side_effect = lambda: len(pages[state["page"]])
        rows.nth.side_effect = lambda index: pages[state["page"]][index]
        messages = MagicMock()
        messages.count.side_effect = lambda: len(threads[state["thread"]])
        messages.nth.side_effect = lambda index: threads[state["thread"]][index]
        next_buttons = MagicMock()
        next_buttons.count.side_effect = lambda: int(state["page"] + 1 < len(pages))
        button = _element()
        next_buttons.nth.return_value = button
        button.click.side_effect = lambda: state.update(page=state["page"] + 1)
        empty = MagicMock()
        empty.count.return_value = 0
        reply_button = _element()
        textbox = _element()

        def locate(selector):
            if selector == "table.F.cf.zt:visible tr.zA:visible":
                return rows
            if selector == "div.adn.ads":
                return messages
            if selector.startswith('div[aria-label="Next results"]'):
                return next_buttons
            if selector.startswith('span[role="link"]'):
                return reply_button
            if selector.startswith('div[role="textbox"]'):
                return textbox
            return empty

        page.locator.side_effect = locate
        playwright = MagicMock()
        browser = (
            playwright.__enter__.return_value.chromium.connect_over_cdp.return_value
        )
        context = MagicMock()
        context.pages = [page]
        browser.contexts = [context]
        student = {
            "id": SID,
            "track": "1",
            "eng_name": "Student",
            "kor_name": "학생",
            "email": "student@example.test",
        }
        monkeypatch.setattr(engine, "sync_playwright", lambda: playwright)
        monkeypatch.setattr(engine, "ensure_chrome_running", lambda log: True)
        monkeypatch.setattr(engine, "dismiss_popups", MagicMock())
        monkeypatch.setattr(
            engine,
            "parse_students",
            lambda: ({SID: student}, {"student": SID}, {student["email"]: SID}),
        )
        monkeypatch.setattr(engine, "get_deadline_dt", lambda task: GRACE)
        monkeypatch.setattr(
            engine,
            "get_late_cutoff_dt",
            lambda *args: datetime(2026, 10, 5, 16, tzinfo=engine.KST),
        )
        monkeypatch.setattr(engine, "send_alert", MagicMock())
        upload = MagicMock()
        monkeypatch.setattr(engine, "upsert_grades_to_sheet", upload)
        log = MagicMock()

        engine.run_grading("0.5", student_filter=student_filter, log=log)

        log.error.assert_not_called()
        assert upload.call_count == 1
        assert len(upload.call_args.args[0]) == 1
        return upload.call_args.args[0][0], page, textbox

    return run


@pytest.mark.parametrize("student_filter", [None, "123"])
@pytest.mark.parametrize(
    "stamps,bodies,subjects,expected_score,expected_date",
    [
        (
            ["Thu, 1 Oct 2026 09:00:00 +0900", "Thu, 1 Oct 2026 22:00:00 +0900"],
            ["https://example.test/old", "https://example.test/new"],
            [f"Assignment 0.5 {SID}", f"Assignment 0.5 [{SID}]"],
            0.9,
            "10/1",
        ),
        (
            ["Fri, 2 Oct 2026 10:00:00 +0900", "Thu, 1 Oct 2026 22:00:00 +0900"],
            ["https://example.test/late", "https://example.test/on-time"],
            [f"Assignment 0.5 {SID}"] * 2,
            1.0,
            "10/1",
        ),
        (
            ["Fri, 2 Oct 2026 10:00:00 +0900", "Sat, 3 Oct 2026 09:00:00 +0900"],
            ["https://example.test/late", ""],
            [f"Assignment 0.5 {SID}"] * 2,
            0.0,
            "10/3",
        ),
        (
            ["Thu, 1 Oct 2026 09:00:00 +0900", "Thu, 1 Oct 2026 22:00:00 +0900"],
            ["https://example.test/old", "https://example.test/new"],
            [f"Assignment 0.5 {SID}", "Assignment 0.5"],
            0.7,
            "10/1",
        ),
    ],
)
def test_auto_grader_compares_all_threads(
    auto_grader, student_filter, stamps, bodies, subjects, expected_score, expected_date
):
    threads = [
        {"subject": subject, "messages": [_message(stamp, body)]}
        for stamp, body, subject in zip(stamps, bodies, subjects)
    ]
    row, page, _ = auto_grader([threads], student_filter)
    assert float(row[4]) == expected_score
    assert row[8] == expected_date
    expected_thread = "thread1"
    assert page.goto.call_args.args[0].endswith(expected_thread)


def test_auto_student_filter_visits_later_pages(auto_grader):
    old = {
        "subject": f"Assignment 0.5 {SID}",
        "messages": [_message("Thu, 1 Oct 2026 09:00:00 +0900")],
    }
    new = {
        "subject": f"Assignment 0.5 [{SID}]",
        "messages": [_message("Thu, 1 Oct 2026 22:00:00 +0900")],
    }
    row, _, _ = auto_grader([[old], [new]], "123")
    assert float(row[4]) == 0.9
    assert row[10] == new["subject"]


def test_auto_selects_latest_on_time_message_within_thread(auto_grader):
    messages = [
        _message("Thu, 1 Oct 2026 09:00:00 +0900"),
        _message("Thu, 1 Oct 2026 22:00:00 +0900", ""),
        _message("Fri, 2 Oct 2026 10:00:00 +0900"),
    ]
    row, _, _ = auto_grader(
        [[{"subject": f"Assignment 0.5 {SID}", "messages": messages}]]
    )
    assert float(row[4]) == 0.0
    assert row[8] == "10/1"
