"""modules/generate_links.py 단위 테스트.

generate_prefilled_url, parse_markdown_table 순수 로직 검증.
"""

import os
import sys
import tempfile
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.generate_links import generate_prefilled_url, parse_markdown_table

# ════════════════════════════════════════════════════════
# generate_prefilled_url
# ════════════════════════════════════════════════════════


class TestGeneratePrefilledUrl:
    """구글 폼 Pre-filled URL 생성 테스트."""

    def test_basic_url_generation(self):
        """기본 URL 생성 및 파라미터 포함 확인."""
        url = generate_prefilled_url("2026300123", "홍길동", "파이썬 (Python)")
        assert "viewform?" in url
        assert "2026300123" in url
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert "entry.861702772" in params
        assert params["entry.861702772"] == ["2026300123"]

    def test_korean_name_encoded(self):
        """한글 이름이 URL 인코딩되어 포함."""
        url = generate_prefilled_url("2026300123", "김철수", "파이썬 (Python)")
        # URL 인코딩된 한글이 포함되어야 함
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert params["entry.2066318256"] == ["김철수"]

    def test_english_name(self):
        """영문 이름 처리."""
        url = generate_prefilled_url("2026300456", "DANGI KABITA", "web-01")
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert params["entry.2066318256"] == ["DANGI KABITA"]
        assert params["entry.898039379"] == ["web-01"]


# ════════════════════════════════════════════════════════
# parse_markdown_table
# ════════════════════════════════════════════════════════


class TestParseMarkdownTable:
    """마크다운 학생 명부 파싱 테스트."""

    def _create_temp_md(self, content):
        """임시 마크다운 파일 생성."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_parse_py_track(self):
        """파이썬 트랙 파싱: 한국어 이름 우선."""
        md_content = (
            "| 강좌번호 | 과목 | 학번 | 성명(영어) | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 468 | 컴사코 | 2026300857 | NGUYEN THI CAM | . | . | . | 응우옌 |\n"
        )
        filepath = self._create_temp_md(md_content)
        try:
            students = parse_markdown_table(filepath, "py")
            assert len(students) == 1
            assert students[0]["student_id"] == "2026300857"
            assert students[0]["name"] == "응우옌"
            assert students[0]["track"] == "파이썬 (Python)"
        finally:
            os.unlink(filepath)

    def test_parse_wb_track_761(self):
        """웹 트랙 761 → web-01 분류."""
        md_content = (
            "| 강좌번호 | 과목 | 학번 | 성명(영어) | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 761 | 웹프로 | 2026300896 | DANGI KABITA | . | . | . | 당기 |\n"
        )
        filepath = self._create_temp_md(md_content)
        try:
            students = parse_markdown_table(filepath, "wb")
            assert len(students) == 1
            assert students[0]["track"] == "web-01"
            assert students[0]["name"] == "DANGI KABITA"
        finally:
            os.unlink(filepath)

    def test_parse_wb_track_762(self):
        """웹 트랙 762 → web-02 분류."""
        md_content = (
            "| 강좌번호 | 과목 | 학번 | 성명(영어) | 추가1 | 추가2 | 추가3 | 한국어이름 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 762 | 웹프로 | 2026300740 | RAI SEMON | . | . | . |  |\n"
        )
        filepath = self._create_temp_md(md_content)
        try:
            students = parse_markdown_table(filepath, "wb")
            assert len(students) == 1
            assert students[0]["track"] == "web-02"
            # 한국어 이름 없으면 영어 이름 사용
            assert students[0]["name"] == "RAI SEMON"
        finally:
            os.unlink(filepath)

    def test_nonexistent_file(self):
        """존재하지 않는 파일 → 빈 리스트 반환."""
        result = parse_markdown_table("/tmp/nonexistent_file_xyz.md", "py")
        assert result == []

    def test_empty_file(self):
        """빈 파일 → 빈 리스트 반환."""
        filepath = self._create_temp_md("")
        try:
            result = parse_markdown_table(filepath, "py")
            assert result == []
        finally:
            os.unlink(filepath)
