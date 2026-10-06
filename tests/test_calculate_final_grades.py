import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize(
    "components, expected_py, expected_web",
    [
        ((100, 100, 0, 0, 0), 50, 60),
        ((0, 100, 0, 0, 0), 10, 20),
        ((50, 80, 10, 20, 40), 45, 50),
    ],
)
def test_main_preserves_midterm_and_course_weights(
    monkeypatch, components, expected_py, expected_web
):
    source = Path(__file__).resolve().parents[1] / "bin/calculate_final_grades.py"
    spec = importlib.util.spec_from_file_location("calculate_final_grades", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    service = MagicMock()
    monkeypatch.setattr(module, "get_sheet_service", lambda *args: service)
    final, midterm, email, peer, attitude = components
    ids = {"468": "2026000007", "761": "2026000101", "762": "2026000201"}
    tabs = {track: [["학번", "기말 점수"], [sid, final]] for track, sid in ids.items()}
    for title, score in zip(
        ["중간고사", "과제_이메일", "과제_상호평가", "수업태도"],
        [midterm, email, peer, attitude],
    ):
        tabs[title] = [["학번", "점수"]] + [[sid, score] for sid in ids.values()]
    values = service.spreadsheets().values()

    def read(**kwargs):
        title = kwargs["range"].split("!")[0].strip("'")
        return MagicMock(execute=MagicMock(return_value={"values": tabs[title]}))

    values.get.side_effect = read
    service.spreadsheets().get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": "최종 성적 통합", "sheetId": 1}}]
    }

    module.main()

    values.update.assert_called_once()
    output = values.update.call_args.kwargs["body"]["values"]
    assert output[0][4] == "중간"
    results = {row[0]: row for row in output[1:]}
    assert len(results) == 3
    for track, row in results.items():
        assert row[3:8] == list(components)
        assert row[8] == (expected_py if track == "468" else expected_web)
    service.spreadsheets().batchUpdate.assert_not_called()
