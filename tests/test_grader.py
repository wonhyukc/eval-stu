"""modules/grader.py 단위 테스트.

parse_email_date, grade_assignment 순수 로직 검증.
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.grader import parse_email_date, grade_assignment

# ════════════════════════════════════════════════════════
# parse_email_date
# ════════════════════════════════════════════════════════


class TestParseEmailDate:
    """이메일 헤더 Date 문자열 파싱 테스트."""

    def test_rfc2822_with_timezone(self):
        """표준 RFC 2822 형식 (+0900) 파싱."""
        result = parse_email_date("Fri, 18 Sep 2026 12:00:00 +0900")
        assert result is not None
        assert result.month == 9
        assert result.day == 18
        assert result.hour == 12

    def test_rfc2822_utc(self):
        """UTC 타임존 포함 RFC 2822 파싱."""
        result = parse_email_date("Mon, 29 Sep 2026 16:05:00 +0000")
        assert result is not None
        # UTC 16:05 → KST 01:05 다음날이지만, parse_email_date는 로컬 시간 반환
        assert result.minute == 5

    def test_invalid_returns_none(self):
        """파싱 불가한 문자열 → None."""
        assert parse_email_date("not-a-date-string") is None

    def test_empty_returns_none(self):
        """빈 문자열 → None."""
        assert parse_email_date("") is None

    def test_none_returns_none(self):
        """None 입력 → None."""
        assert parse_email_date(None) is None


# ════════════════════════════════════════════════════════
# grade_assignment
# ════════════════════════════════════════════════════════


class TestGradeAssignment:
    """과제 채점 로직 테스트."""

    # grader.py 정규식은 학번 8-9자리(\d{8,9})를 기대합니다.
    STUDENT_ID_9 = "202630012"  # 9자리 학번

    def _make_email(self, subject, date_str, is_replied=False):
        return {
            "subject": subject,
            "date_str": date_str,
            "is_replied_by_instructor": is_replied,
        }

    def test_perfect_score(self):
        """정확한 제목 + 기한 내 + 교수 회신 없음 → 3점 만점."""
        email = self._make_email(
            f"과제 0.4 {self.STUDENT_ID_9}",
            "Fri, 18 Sep 2026 12:00:00 +0900",
        )
        deadline = datetime(2026, 9, 20, 23, 59, 59)
        result = grade_assignment(email, "0.4", deadline)
        assert result["total_score"] == 3
        assert result["type1"] == "hw"
        assert result["type2"] == "0.4"
        assert result["reason"] == "Pass (3/3)"

    def test_invalid_title(self):
        """제목 규칙 위반 → 1점 감점."""
        email = self._make_email("제출합니다 0.4", "Fri, 18 Sep 2026 12:00:00 +0900")
        deadline = datetime(2026, 9, 20, 23, 59, 59)
        result = grade_assignment(email, "0.4", deadline)
        assert result["total_score"] == 2
        assert "제목규칙위반" in result["reason"]
        assert result["details"]["title_ok"] is False

    def test_ten_digit_id_fails_title(self):
        """10자리 학번 → 제목규칙 위반 (정규식은 8-9자리만 허용)."""
        email = self._make_email(
            "과제 0.4 2026300123", "Fri, 18 Sep 2026 12:00:00 +0900"
        )
        result = grade_assignment(email, "0.4", None)
        assert result["details"]["title_ok"] is False

    def test_late_submission(self):
        """마감 기한 초과 → 1점 감점."""
        email = self._make_email(
            f"과제 0.4 {self.STUDENT_ID_9}",
            "Mon, 22 Sep 2026 10:00:00 +0900",
        )
        deadline = datetime(2026, 9, 20, 23, 59, 59)
        result = grade_assignment(email, "0.4", deadline)
        assert result["total_score"] == 2
        assert "지각제출" in result["reason"]
        assert result["details"]["time_ok"] is False

    def test_instructor_replied(self):
        """교수 피드백 회신 있음 → 1점 감점."""
        email = self._make_email(
            f"과제 0.4 {self.STUDENT_ID_9}",
            "Fri, 18 Sep 2026 12:00:00 +0900",
            is_replied=True,
        )
        deadline = datetime(2026, 9, 20, 23, 59, 59)
        result = grade_assignment(email, "0.4", deadline)
        assert result["total_score"] == 2
        assert "지적사항회신있음" in result["reason"]
        assert result["details"]["no_reply"] is False

    def test_all_penalties(self):
        """제목위반 + 지각 + 교수회신 → 0점."""
        email = self._make_email(
            "제출", "Mon, 22 Sep 2026 10:00:00 +0900", is_replied=True
        )
        deadline = datetime(2026, 9, 20, 23, 59, 59)
        result = grade_assignment(email, "0.4", deadline)
        assert result["total_score"] == 0

    def test_old_assignment_always_1(self):
        """이전 과제(0.1 등) → 무조건 1점."""
        email = self._make_email(
            f"과제 0.1 {self.STUDENT_ID_9}",
            "Fri, 18 Sep 2026 12:00:00 +0900",
        )
        deadline = datetime(2026, 9, 20, 23, 59, 59)
        result = grade_assignment(email, "0.1", deadline)
        assert result["total_score"] == 1
        assert "이전과제_도착1점" in result["reason"]

    def test_no_deadline_provided(self):
        """마감 미지정 시 기한 내로 처리."""
        email = self._make_email(
            f"과제 0.4 {self.STUDENT_ID_9}",
            "Fri, 18 Sep 2026 12:00:00 +0900",
        )
        result = grade_assignment(email, "0.4", None)
        assert result["details"]["time_ok"] is True

    def test_assignment_title_keyword_korean(self):
        """한국어 키워드 '과제' 인식."""
        email = self._make_email(
            f"과제 0.4 {self.STUDENT_ID_9}",
            "Fri, 18 Sep 2026 12:00:00 +0900",
        )
        result = grade_assignment(email, "0.4", None)
        assert result["details"]["title_ok"] is True

    def test_eight_digit_id_accepted(self):
        """8자리 학번도 정규식에서 허용."""
        email = self._make_email("과제 0.4 20263001", "Fri, 18 Sep 2026 12:00:00 +0900")
        result = grade_assignment(email, "0.4", None)
        assert result["details"]["title_ok"] is True
