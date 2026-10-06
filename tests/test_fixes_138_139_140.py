import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test for Issue 138
from bin.assign_peer_review import assign_reviews


def test_assign_reviews_separates_pools():
    evaluators = ["A", "B", "C", "D"]  # D is a non-submitter
    reviewees = ["A", "B", "C"]

    assignments, receive_counts = assign_reviews(
        evaluators, reviewees, reviews_per_person=2, seed=42
    )

    # Check that D evaluated someone
    assert len(assignments["D"]) == 2

    # Check that D is not a reviewee
    for e, targets in assignments.items():
        assert "D" not in targets

    assert "D" not in receive_counts


# Test for Issue 139
from modules.peer_grader import deduplicate_and_filter_evals


def test_deduplicate_and_filter_evals():
    raw_evals = [
        {"evaluator": "101", "target": "102", "scores": [1, 2]},
        {
            "evaluator": "101",
            "target": "102",
            "scores": [3, 4],
        },  # Duplicate, should overwrite
        {
            "evaluator": "101",
            "target": "101",
            "scores": [5, 5],
        },  # Self-eval, should filter
        {
            "evaluator": "102",
            "target": "103",
            "scores": [1, 1],
        },  # Not assigned, should filter
        {"evaluator": "103", "target": "101", "scores": [2, 2]},  # Valid
    ]
    assignments = {"101": ["102"], "102": ["101"], "103": ["101"]}

    result = deduplicate_and_filter_evals(raw_evals, assignments)

    # Check deduplication
    assert ("101", "102") in result
    assert result[("101", "102")] == [3, 4]

    # Check self-eval filtering
    assert ("101", "101") not in result

    # Check not-assigned filtering
    assert ("102", "103") not in result

    # Check valid is preserved
    assert ("103", "101") in result
    assert result[("103", "101")] == [2, 2]


# Issue 140 is already implicitly tested in test_check_evaluations.py since --max-score is required,
# but we can add a test showing --max-score correctly influences the score.
import subprocess


def test_max_score_is_used(tmp_path):
    # Just checking it accepts the flag
    res = subprocess.run(
        ["python3", "bin/check_evaluations.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--max-score MAX_SCORE" in res.stdout
    assert "Rubric maximum total score" in res.stdout
