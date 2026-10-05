"""modules/score_calculator.py 순수 함수 단위 테스트.

normalize_name_parts, parse_students를 외부 파일 의존 없이 검증.
기존 test_score_calculator.py는 실제 CSV 의존(skipIf)이므로 별도 순수 로직 테스트.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.score_calculator import normalize_name_parts, parse_students

# ════════════════════════════════════════════════════════
# normalize_name_parts
# ════════════════════════════════════════════════════════


class TestNormalizeNameParts:
    """이름 정규화 및 단어 추출 테스트."""

    def test_basic_name(self):
        """기본 영문 이름 → 소문자 단어 집합."""
        result = normalize_name_parts("DANGI KABITA")
        assert result == {"dangi", "kabita"}

    def test_parentheses_removed(self):
        """괄호 안의 내용 제거."""
        result = normalize_name_parts("NGUYEN (Cam) THI")
        assert "cam" not in result
        assert "nguyen" in result
        assert "thi" in result

    def test_brackets_removed(self):
        """대괄호 안의 내용 제거."""
        result = normalize_name_parts("RAI [Semon] TEST")
        assert "semon" not in result
        assert "rai" in result
        assert "test" in result

    def test_special_chars_removed(self):
        """특수문자 제거."""
        result = normalize_name_parts("O'Brien-Smith")
        # 아포스트로피, 하이픈은 제거되고 단어로 분리됨
        assert all(p.isalnum() for p in result)

    def test_empty_name(self):
        """빈 문자열 → 빈 집합."""
        result = normalize_name_parts("")
        assert result == set()

    def test_korean_name(self):
        """한글 이름 처리."""
        result = normalize_name_parts("홍길동")
        assert "홍길동" in result


# ════════════════════════════════════════════════════════
# parse_students
# ════════════════════════════════════════════════════════


class TestParseStudents:
    """마크다운 학생 명부 파싱 테스트."""

    def _create_temp_md(self, content):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_basic_parsing(self):
        """기본 학생 명부 파싱."""
        md = (
            "| 강좌번호 | 과목 | 학번 | 성명 | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 468 | 컴사코 | 2026300857 | NGUYEN THI CAM NGUYEN | . | . | . | 응우옌 |\n"
            "| 468 | 컴사코 | 2026300896 | DANGI KABITA | . | . | . | 당기 |\n"
        )
        filepath = self._create_temp_md(md)
        try:
            students, name_to_id, name_parts = parse_students(filepath)
            assert len(students) == 2
            assert "2026300857" in students
            assert students["2026300857"]["eng"] == "NGUYEN THI CAM NGUYEN"
            assert students["2026300857"]["kor"] == "응우옌"
        finally:
            os.unlink(filepath)

    def test_name_to_id_mapping(self):
        """영문/한글 이름 → 학번 매핑 생성 확인."""
        md = (
            "| 강좌번호 | 과목 | 학번 | 성명 | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 761 | 웹프로 | 2026300740 | RAI SEMON | . | . | . | 라이 |\n"
        )
        filepath = self._create_temp_md(md)
        try:
            _, name_to_id, _ = parse_students(filepath)
            # 영문 이름은 공백 제거 + 소문자로 매핑
            assert name_to_id.get("raisemon") == "2026300740"
            # 한글 이름도 매핑
            assert name_to_id.get("라이") == "2026300740"
        finally:
            os.unlink(filepath)

    def test_header_and_separator_skipped(self):
        """헤더와 구분선(---) 행은 데이터로 파싱되지 않음."""
        md = (
            "| 강좌번호 | 과목 | 학번 | 성명 | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 468 | 컴사코 | 2026300857 | NGUYEN | . | . | . | 응 |\n"
        )
        filepath = self._create_temp_md(md)
        try:
            students, _, _ = parse_students(filepath)
            assert len(students) == 1
            # 구분선이나 헤더가 데이터로 들어가지 않아야 함
            assert "학번" not in students
            assert "---" not in students
        finally:
            os.unlink(filepath)

    def test_name_parts_fuzzy_matching(self):
        """이름 단어 기반 퍼지 매칭용 데이터 생성 확인."""
        md = (
            "| 강좌번호 | 과목 | 학번 | 성명 | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 761 | 웹 | 2026300883 | BASTOLA KAMAL | . | . | . |  |\n"
        )
        filepath = self._create_temp_md(md)
        try:
            _, _, name_parts = parse_students(filepath)
            assert len(name_parts) == 1
            parts_set, sid = name_parts[0]
            assert sid == "2026300883"
            assert "bastola" in parts_set
            assert "kamal" in parts_set
        finally:
            os.unlink(filepath)
