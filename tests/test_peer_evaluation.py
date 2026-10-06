import sys
import os
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.peer_grader import (
    calculate_majority_vote,
    calculate_evaluator_points,
    normalize_final_scores,
)


def test_majority_vote_clear():
    # 3명 중 2명이 동일
    evals = [("eval1", [5, 1]), ("eval2", [5, 1]), ("eval3", [0, 0])]
    maj_scores, has_maj, score_sum = calculate_majority_vote(evals)
    assert maj_scores == (5, 1)
    assert has_maj is True
    assert score_sum == 6.0


def test_majority_vote_tie():
    # 2명이 서로 다른 점수
    evals = [("eval1", [5, 1]), ("eval2", [0, 0])]
    maj_scores, has_maj, score_sum = calculate_majority_vote(evals)
    assert maj_scores == (5, 1)  # tie breaker picks highest sum
    assert has_maj is False
    assert score_sum == 6.0


def test_evaluator_points():
    evals = [("eval1", [5, 1]), ("eval2", [5, 1]), ("eval3", [0, 0])]
    counts = {"eval1": 2, "eval2": 3, "eval3": 3}
    points = calculate_evaluator_points(evals, (5, 1), counts)
    assert points["eval1"] == 1.5  # 3/2
    assert points["eval2"] == 1.0  # 3/3
    assert points["eval3"] == 0.0


def test_final_score_normalized():
    # 제출 9.0 (퍼펙트), 채점 3.0 (퍼펙트) -> 1.0
    sub_ratio, eval_ratio, total = normalize_final_scores(9.0, 3.0, 9.0)
    assert round(sub_ratio, 2) == 0.80
    assert round(eval_ratio, 2) == 0.20
    assert round(total, 2) == 1.00

    # 제출 4.5, 채점 1.5
    sub_ratio, eval_ratio, total = normalize_final_scores(4.5, 1.5, 9.0)
    assert round(sub_ratio, 2) == 0.40
    assert round(eval_ratio, 2) == 0.10
    assert round(total, 2) == 0.50


def test_question_majorities_can_differ_from_every_full_answer():
    evals = [("123", [5, 1, 0]), ("124", [5, 0, 1]), ("125", [0, 1, 1])]
    majority, has_majority, total = calculate_majority_vote(evals)
    assert majority == (5, 1, 1)
    assert has_majority is True
    assert total == 7.0
    points = calculate_evaluator_points(evals, majority, {"123": 3, "124": 3, "125": 3})
    assert points == pytest.approx({"123": 2 / 3, "124": 2 / 3, "125": 2 / 3})


def test_majority_ties_are_resolved_per_question():
    majority, has_majority, total = calculate_majority_vote(
        [("123", [5, 0]), ("124", [0, 1])]
    )
    assert majority == (5, 1)
    assert has_majority is False
    assert total == 6


def test_inconsistent_question_counts_stop_grading():
    with pytest.raises(ValueError):
        calculate_majority_vote([("123", [5, 1]), ("124", [5])])


def test_one_completed_review_out_of_three_earns_one_point():
    points = calculate_evaluator_points([("123", [5, 1])], (5, 1), {"123": 3})
    assert points == {"123": 1.0}
    _, participation, _ = normalize_final_scores(0, points["123"], 6)
    assert participation == pytest.approx(0.2 / 3)


@pytest.mark.parametrize("counts", [{}, {"123": 0}])
def test_unknown_assignment_count_stops_grading(counts):
    with pytest.raises(ValueError):
        calculate_evaluator_points([("123", [5, 1])], (5, 1), counts)
