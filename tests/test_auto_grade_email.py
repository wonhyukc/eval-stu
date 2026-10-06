"""auto_grade_email.py 핵심 함수 단위 테스트.

Playwright/Gmail 의존 없이 순수 로직(날짜 파싱, 채점 판정, 답장 본문 생성)만 검증한다.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bin.auto_grade_email import (
    KST,
    build_reply_body,
    evaluate_submission,
    parse_gmail_date,
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
