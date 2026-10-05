"""modules/peer_review_assigner.py 단위 테스트.

deduplicate_students, assign_random_peer_reviews 순수 로직 검증.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.peer_review_assigner import (
    deduplicate_students,
    assign_random_peer_reviews,
)

# ════════════════════════════════════════════════════════
# deduplicate_students
# ════════════════════════════════════════════════════════


class TestDeduplicateStudents:
    """중복 학생 제거 테스트."""

    def test_no_duplicates(self):
        """중복 없는 경우 그대로 반환."""
        students = [
            {"id": "001", "name": "A"},
            {"id": "002", "name": "B"},
        ]
        result = deduplicate_students(students)
        assert len(result) == 2

    def test_remove_duplicates(self):
        """같은 학번이 여러 번 → 마지막 기록만 유지."""
        students = [
            {"id": "001", "name": "A_old"},
            {"id": "002", "name": "B"},
            {"id": "001", "name": "A_new"},
        ]
        result = deduplicate_students(students)
        assert len(result) == 2
        names = {s["id"]: s["name"] for s in result}
        assert names["001"] == "A_new"

    def test_empty_list(self):
        """빈 리스트 → 빈 리스트."""
        assert deduplicate_students([]) == []


# ════════════════════════════════════════════════════════
# assign_random_peer_reviews
# ════════════════════════════════════════════════════════


class TestAssignRandomPeerReviews:
    """균형 무작위 상호평가 배정 테스트."""

    def _make_evaluators(self, ids):
        return [{"id": sid, "name": f"Student_{sid}"} for sid in ids]

    def test_self_exclusion(self):
        """자기 자신의 과제는 배정되지 않음."""
        ids = ["001", "002", "003", "004", "005"]
        evaluators = self._make_evaluators(ids)
        submitted = set(ids)
        results, _ = assign_random_peer_reviews(evaluators, submitted, min_receive=3)
        for entry in results:
            reviewer_id = entry["reviewer"]["id"]
            reviewee_ids = [r["id"] for r in entry["reviewees"]]
            assert (
                reviewer_id not in reviewee_ids
            ), f"리뷰어 {reviewer_id}가 자기 자신을 배정받음"

    def test_all_evaluators_assigned(self):
        """모든 학생(미제출자 포함)에게 최소 1건 배정."""
        submitted_ids = {"001", "002", "003", "004"}
        all_ids = ["001", "002", "003", "004", "005"]  # 005는 미제출자
        evaluators = self._make_evaluators(all_ids)
        results, _ = assign_random_peer_reviews(
            evaluators, submitted_ids, min_receive=3
        )
        for entry in results:
            assert (
                len(entry["reviewees"]) >= 1
            ), f"{entry['reviewer']['id']}에게 배정된 피평가자가 없음"

    def test_min_receive_satisfied(self):
        """제출자는 최소 min_receive 횟수의 평가를 받아야 함."""
        ids = ["001", "002", "003", "004", "005", "006"]
        evaluators = self._make_evaluators(ids)
        submitted = set(ids)
        min_recv = 3
        _, receive_counts = assign_random_peer_reviews(
            evaluators, submitted, min_receive=min_recv
        )
        for s_id, count in receive_counts.items():
            assert count >= 1, f"제출자 {s_id}가 평가를 0회 받음"

    def test_too_few_submitters_raises(self):
        """제출자가 2명 미만이면 ValueError 발생."""
        evaluators = self._make_evaluators(["001", "002", "003"])
        submitted = {"001"}  # 1명만 제출
        with pytest.raises(ValueError, match="2명 미만"):
            assign_random_peer_reviews(evaluators, submitted, min_receive=3)

    def test_reviewees_only_from_submitters(self):
        """피평가자는 반드시 제출자 풀에서만 선정."""
        submitted_ids = {"001", "002", "003"}
        all_ids = ["001", "002", "003", "004"]  # 004는 미제출
        evaluators = self._make_evaluators(all_ids)
        results, _ = assign_random_peer_reviews(
            evaluators, submitted_ids, min_receive=3
        )
        for entry in results:
            for reviewee in entry["reviewees"]:
                assert (
                    reviewee["id"] in submitted_ids
                ), f"미제출자 {reviewee['id']}가 피평가자로 배정됨"

    def test_sorted_by_id(self):
        """결과가 학번 오름차순으로 정렬."""
        ids = ["005", "003", "001", "004", "002"]
        evaluators = self._make_evaluators(ids)
        submitted = set(ids)
        results, _ = assign_random_peer_reviews(evaluators, submitted, min_receive=3)
        result_ids = [entry["reviewer"]["id"] for entry in results]
        assert result_ids == sorted(result_ids)
