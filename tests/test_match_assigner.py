"""modules/match_assigner.py 단위 테스트.

parse_markdown_table, assign_peers_for_class 순수 로직 검증.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.match_assigner import parse_markdown_table, assign_peers_for_class

# ════════════════════════════════════════════════════════
# parse_markdown_table
# ════════════════════════════════════════════════════════


class TestParseMarkdownTable:
    """마크다운 테이블 파싱 테스트."""

    def _create_temp_md(self, content):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_basic_parsing(self):
        """기본 마크다운 테이블 파싱."""
        md = (
            "| 학번 | 이름 | 분반 |\n"
            "|---|---|---|\n"
            "| 2026300857 | 홍길동 | 04 |\n"
            "| 2026300896 | 김철수 | 01 |\n"
        )
        filepath = self._create_temp_md(md)
        try:
            data = parse_markdown_table(filepath)
            assert len(data) == 2
            assert data[0]["학번"] == "2026300857"
            assert data[1]["이름"] == "김철수"
        finally:
            os.unlink(filepath)

    def test_skips_non_table_lines(self):
        """테이블이 아닌 줄은 무시."""
        md = (
            "# 학생 명부\n"
            "\n"
            "아래는 명부입니다.\n"
            "\n"
            "| 학번 | 이름 |\n"
            "|---|---|\n"
            "| 2026300857 | 홍길동 |\n"
        )
        filepath = self._create_temp_md(md)
        try:
            data = parse_markdown_table(filepath)
            assert len(data) == 1
            assert data[0]["학번"] == "2026300857"
        finally:
            os.unlink(filepath)


# ════════════════════════════════════════════════════════
# assign_peers_for_class
# ════════════════════════════════════════════════════════


class TestAssignPeersForClass:
    """분반 내 상호평가 배정 테스트."""

    def _make_students(self, ids):
        return [{"학번": sid, "이름": f"학생{sid}"} for sid in ids]

    def test_self_exclusion(self):
        """자기 자신은 배정 대상에서 제외."""
        students = self._make_students(["001", "002", "003", "004"])
        assignments = assign_peers_for_class(students, students, num_peers=3)
        for evaluator_id, assigned in assignments.items():
            for target in assigned:
                assert (
                    target["학번"] != evaluator_id
                ), f"평가자 {evaluator_id}가 자기 자신을 배정받음"

    def test_correct_peer_count(self):
        """각 평가자에게 정확히 num_peers명 배정."""
        students = self._make_students(["001", "002", "003", "004", "005"])
        assignments = assign_peers_for_class(students, students, num_peers=3)
        for evaluator_id, assigned in assignments.items():
            assert (
                len(assigned) == 3
            ), f"평가자 {evaluator_id}: {len(assigned)}명 배정 (3명 기대)"

    def test_no_duplicate_within_evaluator(self):
        """같은 평가자에게 동일 피평가자가 중복 배정되지 않음 (타겟 풀이 충분할 때)."""
        students = self._make_students(["001", "002", "003", "004", "005", "006"])
        assignments = assign_peers_for_class(students, students, num_peers=3)
        for evaluator_id, assigned in assignments.items():
            assigned_ids = [t["학번"] for t in assigned]
            assert len(assigned_ids) == len(
                set(assigned_ids)
            ), f"평가자 {evaluator_id}에 중복 배정 발생: {assigned_ids}"

    def test_empty_targets(self):
        """타겟 리스트가 비어있으면 모든 평가자에게 빈 배정."""
        evaluators = self._make_students(["001", "002"])
        assignments = assign_peers_for_class(evaluators, [], num_peers=3)
        for evaluator_id, assigned in assignments.items():
            assert assigned == []
