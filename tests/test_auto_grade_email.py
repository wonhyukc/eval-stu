"""auto_grade_email.py 핵심 함수 단위 테스트.

Playwright/Gmail 의존 없이 순수 로직(날짜 파싱, 채점 판정, 답장 본문 생성)만 검증한다.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from urllib.parse import unquote

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bin.auto_grade_email import (
    KST,
    build_reply_body,
    evaluate_submission,
    parse_gmail_date,
    build_search_url,
    get_thread_id,
    resolve_student_id,
    build_grade_rows,
    sync_grade_rows,
    get_deadline_dt,
    get_late_cutoff_dt,
)

# ════════════════════════════════════════════════════════
# parse_gmail_date — 다중 포맷 파싱 테스트
# ════════════════════════════════════════════════════════


class TestParseGmailDate:
    """Gmail 타임스탬프 문자열 → KST datetime 변환 테스트."""

    def test_rfc2822_english(self):
        """RFC 2822 영어 형식 (Gmail 영어 설정)."""
        result = parse_gmail_date("Thu, Oct 1, 2026, 10:55 PM")
        assert result is not None
        assert result.tzinfo is not None
        assert result.month == 10
        assert result.day == 1
        assert result.hour == 22
        assert result.minute == 55

    @pytest.mark.parametrize(
        "raw,hour",
        [
            ("Fri, Oct 2, 2026, 1:05 PM", 13),
            ("Fri, Oct 2, 2026, 1:05 AM", 1),
            ("Oct 2, 2026, 12:05 PM", 12),
            ("Oct 2, 2026, 12:05 AM", 0),
        ],
    )
    def test_english_am_pm_hour(self, raw, hour):
        assert parse_gmail_date(raw) == datetime(2026, 10, 2, hour, 5, tzinfo=KST)

    def test_web2_afternoon_submission_is_after_class_start(self, monkeypatch):
        from bin import auto_grade_email as engine

        monkeypatch.setattr(
            engine,
            "get_deadline_dt",
            lambda *args: datetime(2026, 10, 2, 0, 15, tzinfo=KST),
        )
        monkeypatch.setattr(
            engine,
            "get_late_cutoff_dt",
            lambda *args: datetime(2026, 10, 5, 13, 0, tzinfo=KST),
        )
        score, _, _, _ = evaluate_submission(
            "Assignment 0.5 2026000123",
            "https://example.test/submission",
            {"id": "2026000123", "track": "2"},
            parse_gmail_date("Mon, Oct 5, 2026, 1:05 PM"),
            "0.5",
        )
        assert score == 0.0

    def test_rfc2822_with_timezone(self):
        """UTC 타임존 포함 → KST 변환."""
        result = parse_gmail_date("Mon, 29 Sep 2026 16:05:00 +0000")
        assert result is not None
        # UTC 16:05 → KST 01:05 (다음날)
        kst_result = result.astimezone(KST)
        assert kst_result.hour == 1
        assert kst_result.minute == 5

    def test_korean_format_am(self):
        """한국어 Gmail 포맷 (오전)."""
        result = parse_gmail_date("2026년 9월 28일 (일) 오전 9:20")
        assert result is not None
        assert result.hour == 9
        assert result.minute == 20

    def test_korean_format_pm(self):
        """한국어 Gmail 포맷 (오후)."""
        result = parse_gmail_date("9월 28일 (일) 오후 3:11")
        assert result is not None
        assert result.hour == 15
        assert result.minute == 11

    def test_korean_format_noon(self):
        """한국어 Gmail 오후 12시 (정오)."""
        result = parse_gmail_date("2026년 10월 1일 (수) 오후 12:00")
        assert result is not None
        assert result.hour == 12

    def test_korean_format_midnight(self):
        """한국어 Gmail 오전 12시 (자정)."""
        result = parse_gmail_date("2026년 10월 1일 (수) 오전 12:30")
        assert result is not None
        assert result.hour == 0
        assert result.minute == 30

    def test_dateutil_english_comma(self):
        """dateutil 파서: 'Sep 28, 2026, 9:20 AM' 형식."""
        result = parse_gmail_date("Sep 28, 2026, 9:20 AM")
        assert result is not None
        assert result.month == 9
        assert result.day == 28
        assert result.hour == 9

    def test_empty_string_returns_none(self):
        """빈 문자열 → None."""
        assert parse_gmail_date("") is None
        assert parse_gmail_date("   ") is None

    def test_unparseable_returns_none(self):
        """파싱 불가 문자열 → None."""
        assert parse_gmail_date("not-a-date") is None

    def test_result_is_kst(self):
        """결과 타임존이 KST(+09:00)인지 확인."""
        result = parse_gmail_date("Oct 1, 2026, 10:00 AM")
        assert result is not None
        assert result.utcoffset() == timedelta(hours=9)


# ════════════════════════════════════════════════════════
# evaluate_submission — 채점 판정 테스트
# ════════════════════════════════════════════════════════


class TestEvaluateSubmission:
    """이메일 과제 채점 로직 테스트."""

    # 표준 학생 정보 fixture
    STUDENT_WEB2 = {
        "id": "2026300896",
        "eng_name": "DANGI KABITA",
        "kor_name": "당기 카비타",
        "track": "2",
    }
    STUDENT_PY = {
        "id": "2026300857",
        "eng_name": "NGUYEN THI CAM NGUYEN",
        "kor_name": "응우옌 티 깜 응우옌",
        "track": "4",
    }

    def _make_dt(self, day: int, hour: int = 10) -> datetime:
        """2026년 10월 KST datetime 생성 헬퍼."""
        return datetime(2026, 10, day, hour, 0, 0, tzinfo=KST)

    def test_exact_format_ontime(self):
        """정확한 형식 + 정시 제출 → 1.0점."""
        score, reason_en, reason_ko, _ = evaluate_submission(
            subject="과제 0.5 2026300896",
            body_text="안녕하세요 교수님, 과제 0.5 제출합니다.\nhttps://example.com/my-page",
            student_info=self.STUDENT_WEB2,
            email_dt=self._make_dt(1, 10),  # 정규마감 전
            task_id="0.5",
        )
        assert score == 1.0
        assert "Exact" in reason_en

    def test_minor_format_ontime(self):
        """학번+과제명 있지만 정확한 형식 아님 → 0.9점."""
        score, reason_en, _, _ = evaluate_submission(
            subject="[과제 0.5] 2026300896 DANGI KABITA",
            body_text="제출합니다 https://example.com",
            student_info=self.STUDENT_WEB2,
            email_dt=self._make_dt(1),
            task_id="0.5",
        )
        assert score == 0.9
        assert "Minor" in reason_en

    def test_empty_body_zero(self):
        """본문 미작성 (30자 미만 + URL 없음) → 0.0점."""
        score, reason_en, _, _ = evaluate_submission(
            subject="과제 0.5 2026300896",
            body_text="> On Oct 1, wrote:\n> 인용문만",
            student_info=self.STUDENT_WEB2,
            email_dt=self._make_dt(1),
            task_id="0.5",
        )
        assert score == 0.0
        assert "Empty Body" in reason_en

    def test_body_with_url_only(self):
        """본문은 짧지만 URL 포함 → 본문 검증 통과."""
        score, _, _, _ = evaluate_submission(
            subject="과제 0.5 2026300896",
            body_text="https://example.com/my-submission",
            student_info=self.STUDENT_WEB2,
            email_dt=self._make_dt(1),
            task_id="0.5",
        )
        assert score > 0.0  # URL만 있으면 본문 미달은 아님

    def test_late_with_id(self):
        """지각 제출 (마감 후, 다음 수업 전) + 학번 있음 → 0.5점."""
        score, reason_en, _, _ = evaluate_submission(
            subject="assignment 0.5 2026300896",
            body_text="This is my assignment submission for 0.5\nhttps://example.com",
            student_info=self.STUDENT_WEB2,
            email_dt=self._make_dt(4, 10),  # 지각 범위 내
            task_id="0.5",
        )
        assert score == 0.5
        assert "Late" in reason_en

    def test_no_student_info(self):
        """student_info가 None이어도 크래시 없이 처리."""
        score, reason_en, _, _ = evaluate_submission(
            subject="과제 0.5",
            body_text="안녕하세요 과제 제출합니다 이것은 충분히 긴 본문입니다.",
            student_info=None,
            email_dt=self._make_dt(1),
            task_id="0.5",
        )
        # 크래시 없이 점수 반환 확인
        assert isinstance(score, float)

    @pytest.mark.parametrize(
        "subject,info,day,expected",
        [
            ("Assignment 0.5 (896)", STUDENT_WEB2, 1, 0.7),
            ("Assignment 0.5 (896)", STUDENT_WEB2, 4, 0.2),
            ("Assignment 0.5", None, 1, 0.7),
            ("Assignment 0.50 2026300896", STUDENT_WEB2, 1, 0.7),
            ("Assignment 0.5 120263008960", STUDENT_WEB2, 1, 0.7),
            ("Assignment 0.5 2026300857", STUDENT_WEB2, 1, 0.7),
        ],
    )
    def test_missing_or_wrong_id_cannot_receive_exact_score(
        self, subject, info, day, expected
    ):
        assert (
            evaluate_submission(
                subject, "https://example.test/work", info, self._make_dt(day), "0.5"
            )[0]
            == expected
        )


def test_search_url_preserves_entire_query_in_one_path_segment():
    query = '"0.7" after:2026/10/12 from:student@example.test'
    encoded = build_search_url(query).split("#search/", 1)[1]
    assert "/" not in encoded
    assert unquote(encoded) == query


@pytest.mark.parametrize("attribute", ["data-legacy-thread-id", "data-thread-id"])
@pytest.mark.parametrize("nested", [False, True])
def test_thread_id_on_row_or_subject_element(attribute, nested):
    row = MagicMock()
    row.get_attribute.side_effect = lambda key: (
        "abc123" if key == attribute and not nested else None
    )
    empty = MagicMock()
    empty.count.return_value = 0
    child = MagicMock()
    child.count.return_value = 1
    child.first.get_attribute.return_value = "abc123"
    row.locator.side_effect = lambda selector: (
        child if nested and selector == f"[{attribute}]" else empty
    )
    assert get_thread_id(row) == "abc123"


@pytest.mark.parametrize(
    "subject,email,students,expected",
    [
        ("Assignment 0.7 (123)", "", {"2026000123": {}}, "2026000123"),
        ("Assignment 0.123", "", {"2026000123": {}}, None),
        ("Assignment 0.7 (123)", "", {"2026000123": {}, "2027000123": {}}, None),
        ("Assignment 0.7 2026000124", "", {"2026000123": {}}, None),
        (
            "Assignment 0.7 2026000124",
            "S@EXAMPLE.TEST",
            {"2026000123": {}},
            "2026000123",
        ),
    ],
)
def test_resolve_student_uses_unique_roster_ids(subject, email, students, expected):
    assert (
        resolve_student_id(
            subject, email, "", students, {"s@example.test": "2026000123"}, {}
        )
        == expected
    )


def test_missing_rows_respect_track_and_individual_filters():
    students = {
        "2026000123": {"id": "2026000123", "track": "1"},
        "2026000124": {"id": "2026000124", "track": "1"},
        "2026000125": {"id": "2026000125", "track": "4"},
    }
    item = {
        "student_info": students["2026000123"],
        "score": 0.7,
        "reason_en": "Missing Student ID or 0.x in Subject",
        "date": "10/15 22:43",
        "subject": "Assignment 0.7 (123)",
    }
    rows = build_grade_rows([item], students, "0.7", track="1")
    assert [(r[2], r[4]) for r in rows] == [
        ("2026000123", "0.70"),
        ("2026000124", "0.00"),
    ]
    assert rows[1][7] == "No submission"
    only_student = build_grade_rows([], students, "0.7", student_id="2026000125")
    assert len(only_student) == 1
    assert only_student[0][7] == "미제출"
    assert build_grade_rows([], students, "0.7", student_id="unknown") == []


def test_sync_failure_prevents_later_tracks(monkeypatch):
    from bin import auto_grade_email as engine

    upload = MagicMock(return_value=False)
    monkeypatch.setattr(engine, "upsert_grades_to_sheet", upload)
    with pytest.raises(RuntimeError, match="답장 발송 중단"):
        sync_grade_rows([[0, "7", "123", "1"], [0, "7", "124", "2"]])
    assert upload.call_count == 1
    assert upload.call_args.kwargs == {"course": "web1"}


def test_sync_spaces_multiple_courses_to_avoid_quota_errors(monkeypatch):
    from bin import auto_grade_email as engine

    upload = MagicMock(return_value=True)
    sleep = MagicMock()
    monkeypatch.setattr(engine, "upsert_grades_to_sheet", upload)
    monkeypatch.setattr(engine.time, "sleep", sleep)
    sync_grade_rows([[0, "7", "123", "1"], [0, "7", "124", "2"]])
    assert [call.kwargs["course"] for call in upload.call_args_list] == ["web1", "web2"]
    sleep.assert_called_once_with(65)


def test_cli_reports_failed_run_to_shell(monkeypatch):
    from bin import auto_grade_email as engine

    monkeypatch.setattr(engine.sys, "argv", ["auto_grade_email.py", "0.7"])
    monkeypatch.setattr(engine, "setup_logging", lambda task: (MagicMock(), None))
    monkeypatch.setattr(engine, "run_grading", MagicMock(return_value=False))
    with pytest.raises(SystemExit) as exc:
        engine.main()
    assert exc.value.code == 1


def test_schedule_requires_ssot_and_uses_semester_year(tmp_path, monkeypatch):
    from bin import auto_grade_email as engine

    monkeypatch.setattr(engine, "BASE_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        get_deadline_dt("0.7")
    (tmp_path / "5input").mkdir()
    schedule = tmp_path / "5input/deadline.csv"
    schedule.write_text(
        "week,lab-deadline,email-deadline\n7,10/19,10/16 0:00\n", encoding="utf-8"
    )
    assert get_deadline_dt("0.7") == datetime(2026, 10, 16, 0, 15, tzinfo=KST)
    assert get_late_cutoff_dt("0.7", "1") == datetime(2026, 10, 19, 16, tzinfo=KST)
    with pytest.raises(ValueError, match="유일하게"):
        get_deadline_dt("0.8")


# ════════════════════════════════════════════════════════
# build_reply_body — 답장 본문 생성 테스트
# ════════════════════════════════════════════════════════


class TestBuildReplyBody:
    """트랙별 언어 정책에 따른 답장 본문 생성 테스트."""

    def test_web_track_english(self):
        """E트랙 (web1/web2) → 영문 답장."""
        item = {
            "student_info": {
                "id": "2026300896",
                "eng_name": "DANGI KABITA",
                "kor_name": "당기 카비타",
                "track": "2",
            },
            "score": 1.0,
            "reason_en": "On-time & Exact Format",
            "reason_ko": "정상 제출",
        }
        body = build_reply_body(item, "0.5")
        assert "Dear DANGI KABITA" in body
        assert "1.0 / 1.0" in body
        assert "Wonhyuk William Chung" in body
        # 한글이 포함되지 않아야 함
        assert "안녕하세요" not in body

    def test_py_track_korean(self):
        """K트랙 (py/4반) → 한글 답장."""
        item = {
            "student_info": {
                "id": "2026300857",
                "eng_name": "NGUYEN THI CAM NGUYEN",
                "kor_name": "응우옌 티 깜 응우옌",
                "track": "4",
            },
            "score": 1.0,
            "reason_en": "On-time & Exact Format",
            "reason_ko": "정상 제출 (기한내/정확한 양식)",
        }
        body = build_reply_body(item, "0.5")
        assert "안녕하세요" in body
        assert "응우옌 티 깜 응우옌" in body
        assert "정원혁 드림" in body
        # 영문 서명이 포함되지 않아야 함
        assert "Wonhyuk William Chung" not in body

    def test_zero_score_empty_body_en(self):
        """0점 (본문 미달) E트랙 → 영문 + 재제출 안내."""
        item = {
            "student_info": {
                "id": "2026300883",
                "eng_name": "BASTOLA KAMAL",
                "kor_name": "",
                "track": "1",
            },
            "score": 0.0,
            "reason_en": "Empty Body / Quoted Text Only",
            "reason_ko": "본문 미작성(단순 회신)",
        }
        body = build_reply_body(item, "0.5")
        assert "0.0 / 1.0" in body
        assert "re-submit" in body.lower() or "content" in body.lower()

    def test_zero_score_late_cutoff_ko(self):
        """0점 (지각 초과) K트랙 → 한글 + 마감 초과 안내."""
        item = {
            "student_info": {
                "id": "2026300859",
                "eng_name": "NGUYEN VAN QUY",
                "kor_name": "응우옌 반 쿠이",
                "track": "4",
            },
            "score": 0.0,
            "reason_en": "Rejected (Past late cutoff)",
            "reason_ko": "불인정 (지각 마감 초과)",
        }
        body = build_reply_body(item, "0.5")
        assert "0.0 / 1.0" in body
        assert "마감" in body

    def test_late_submission_en(self):
        """0.5점 (지각) E트랙 → 영문 + 향후 주의 안내."""
        item = {
            "student_info": {
                "id": "2026300740",
                "eng_name": "RAI SEMON",
                "kor_name": "",
                "track": "1",
            },
            "score": 0.5,
            "reason_en": "Late submission (Before next class)",
            "reason_ko": "지각 제출",
        }
        body = build_reply_body(item, "0.5")
        assert "0.5 / 1.0" in body
        assert "Dear RAI SEMON" in body
