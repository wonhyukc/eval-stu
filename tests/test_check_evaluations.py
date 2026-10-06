import csv
import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

from modules.peer_grader import (
    build_track_map,
    normalize_student_id,
    load_review_assignments,
)


@pytest.fixture
def offline_engine(peer_project, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "bin" / "check_evaluations.py"
    spec = importlib.util.spec_from_file_location("check_evaluations", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(peer_project / "bin" / source.name))
    monkeypatch.setattr(module, "load_settings", lambda: {})
    credentials = Mock(side_effect=AssertionError("실제 인증 호출 금지"))
    monkeypatch.setattr(module.Credentials, "from_service_account_file", credentials)
    upload = Mock(return_value=True)
    monkeypatch.setattr("modules.sheet_updater.upsert_grades_to_sheet", upload)
    return module, upload, credentials


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026000123", "123"),
        ("123", "123"),
        ("  '2026000007 ", "007"),
        ("007", "007"),
        (7, "007"),
        ("", ""),
        (None, ""),
        ("student123", ""),
    ],
)
def test_normalize_student_id(raw, expected):
    assert normalize_student_id(raw) == expected


@pytest.fixture
def peer_project(tmp_path):
    roster_dir = tmp_path / "5input" / "students"
    roster_dir.mkdir(parents=True)
    header = "| 강좌번호 | 학번 |\n| --- | --- |\n"
    (roster_dir / "py-students.md").write_text(
        header + "| 14712 | 2026000007 |\n| 14712 | 2026000008 |\n"
    )
    (roster_dir / "wb-students.md").write_text(
        header
        + "| 15143 | 2026000101 |\n| 15143 | 2026000102 |\n"
        + "| 15144 | 2026000201 |\n| 15144 | 2026000202 |\n"
    )
    output = tmp_path / "output"
    output.mkdir()
    assignments = tmp_path / "9output"
    assignments.mkdir()
    for track, pair in [
        ("14712", ("007", "008")),
        ("15143", ("101", "102")),
        ("15144", ("201", "202")),
    ]:
        first, second = pair
        (assignments / f"week6_peer_review_assignments_{track}.md").write_text(
            "| No | Evaluator ID | Status | Reviewee 1 |\n| --- | --- | --- | --- |\n"
            f"| 1 | **{first}** | Submitted | [{second}](https://example.com) |\n"
            f"| 2 | **{second}** | Submitted | [{first}](https://example.com) |\n"
        )
    with (output / "sample_data.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["평가 주차", "평가자 학번", "피평가자 학번", "Q1 점수"])
        for evaluator, target in [("007", "008"), ("101", "102"), ("201", "202")]:
            writer.writerows(
                [
                    ["6주차", evaluator, "2026000" + target, "5"],
                    ["6주차", "2026000" + evaluator, target, "5"],
                    ["6주차", target, evaluator, "5"],
                ]
            )
        writer.writerow(["6주차", "999", "999", "5"])
    return tmp_path


def test_track_map_uses_same_three_digit_keys(peer_project):
    assert build_track_map(peer_project) == {
        "007": "4",
        "008": "4",
        "101": "1",
        "102": "1",
        "201": "2",
        "202": "2",
    }


@pytest.mark.parametrize(
    "course, expected_ids, tracks",
    [
        ("py", {"007", "008"}, {"4"}),
        ("web1", {"101", "102"}, {"1"}),
        ("web2", {"201", "202"}, {"2"}),
        ("web", {"101", "102", "201", "202"}, {"1", "2"}),
    ],
)
def test_main_groups_mixed_ids_and_filters_course(
    peer_project, monkeypatch, offline_engine, course, expected_ids, tracks
):
    module, upload, credentials = offline_engine
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_evaluations.py",
            "--offline",
            "--upload",
            "-c",
            course,
            "-w",
            "06",
            "--max-score",
            "5",
        ],
    )

    module.main()

    with (peer_project / "output" / f"{course}-06-peer-score.csv").open(
        encoding="utf-8-sig"
    ) as stream:
        results = list(csv.DictReader(stream))
    assert {r["학번"] for r in results} == expected_ids
    assert {r["분반"] for r in results} == tracks
    assert all(float(r["최종획득점수(1.0만점)"]) == 1.0 for r in results)
    upload.assert_called_once()
    rows = upload.call_args.args[0]
    assert {r[1] for r in rows} == expected_ids
    assert {r[2] for r in rows} == tracks
    assert upload.call_args.kwargs["course"] == course
    credentials.assert_not_called()


def test_main_uses_assignment_count_and_excludes_unassigned_and_duplicate_reviews(
    peer_project, offline_engine, monkeypatch
):
    roster = peer_project / "5input/students/py-students.md"
    roster.write_text(
        roster.read_text() + "| 14712 | 2026000009 |\n| 14712 | 2026000010 |\n"
    )
    assignment = peer_project / "9output/week6_peer_review_assignments_14712.md"
    assignment.write_text(
        "| Evaluator / 평가자 (학번) | Reviewee 1 | Reviewee 2 | Reviewee 3 |\n"
        "| --- | --- | --- | --- |\n"
        "| **2026000007** | [008](https://example.com) | 009 | 010 |\n"
        "| 008 | 007 | N/A | N/A |\n"
        "| 009 | 007 | N/A | N/A |\n"
        "| 010 | 007 | N/A | N/A |\n"
    )
    with (peer_project / "output/sample_data.csv").open("a", newline="") as stream:
        csv.writer(stream).writerow(["6주차", "007", "999", "999"])
    module, upload, _ = offline_engine
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_evaluations.py",
            "--offline",
            "--upload",
            "-w",
            "6",
            "--max-score",
            "5",
        ],
    )
    module.main()
    with (peer_project / "output/py-6-peer-score.csv").open(
        encoding="utf-8-sig"
    ) as stream:
        results = {r["학번"]: r for r in csv.DictReader(stream)}
    assert float(results["007"]["평가점수(가중치0.2)"]) == pytest.approx(0.067)
    assert float(results["007"]["최종획득점수(1.0만점)"]) == pytest.approx(0.867)
    assert float(results["008"]["제출점수(가중치0.8)"]) == 0.8
    assert float(results["009"]["최종획득점수(1.0만점)"]) == 0
    assert float(results["010"]["최종획득점수(1.0만점)"]) == 0
    assert "999" not in results
    upload.assert_called_once()


def test_missing_assignment_file_stops_before_authentication_and_upload(
    peer_project, offline_engine, monkeypatch
):
    for path in (peer_project / "9output").glob("*.md"):
        path.unlink()
    module, upload, credentials = offline_engine
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_evaluations.py", "--offline", "--upload", "--max-score", "5"],
    )
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    credentials.assert_not_called()
    upload.assert_not_called()


def test_invalid_assignment_table_stops_instead_of_inventing_counts(tmp_path):
    path = tmp_path / "invalid.md"
    path.write_text("| Evaluator ID | Reviewee 1 | Reviewee 2 |\n| 007 | 008 | 008 |\n")
    with pytest.raises(ValueError):
        load_review_assignments([path])


def test_no_responses_records_assigned_evaluators_as_zero(
    peer_project, offline_engine, monkeypatch
):
    (peer_project / "output/sample_data.csv").write_text("")
    module, upload, _ = offline_engine
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_evaluations.py",
            "--offline",
            "--upload",
            "-w",
            "6",
            "--max-score",
            "5",
        ],
    )
    module.main()
    rows = upload.call_args.args[0]
    assert {r[1] for r in rows} == {"007", "008"}
    assert all(r[3] == 0 for r in rows)
