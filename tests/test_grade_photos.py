"""tests/test_grade_photos.py — grade_photos 단위 테스트.

#119 수정 검증: 사진 채점이 공통 upsert_grades_to_sheet를 사용하여
A:M 13열 전체를 안전하게 갱신하는지, 기존 행의 M열(이의제기) 및
수식(E열/K열)이 보존되는지 테스트합니다.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bin.grade_photos import build_score_rows, resolve_uploader

# ──────────────────────────────────────────────────────────────────────
# build_score_rows 단위 테스트
# ──────────────────────────────────────────────────────────────────────


def test_build_score_rows_web1_language():
    """웹 1반 행은 영어 사유, 트랙='1', type1='hw', type2='0.p'."""
    students = [{"sid": "2026300741", "name": "BASTOLA KAMAL"}]
    uploaders = {"BASTOLA KAMAL"}
    rows = build_score_rows("web1", students, uploaders, "10/6")
    assert len(rows) == 1
    r = rows[0]
    # 11열 구조: [no, wk, sid, track, score, type1, type2, reason, date, name, subj]
    assert len(r) == 11
    assert r[0] == ""  # no (upsert 시 자동 부여)
    assert r[1] == "1"  # wk
    assert r[2] == "741"  # sid 뒤 3자리
    assert r[3] == "1"  # track
    assert r[4] == "1.00"  # score
    assert r[5] == "hw"  # type1
    assert r[6] == "0.p"  # type2
    assert "submitted" in r[7].lower()  # 영어 사유
    assert r[8] == "10/6"  # date


def test_build_score_rows_py_language():
    """파이썬 4반 행은 한국어 사유, 트랙='4'."""
    students = [{"sid": "2026300857", "name": "NGUYEN THI CAM NGUYEN"}]
    uploaders = {"NGUYEN THI CAM NGUYEN"}
    rows = build_score_rows("py", students, uploaders, "10/6")
    r = rows[0]
    assert r[3] == "4"  # track
    assert r[4] == "1.00"  # score
    assert "포토" in r[7] or "제출" in r[7]  # 한국어 사유


def test_build_score_rows_not_submitted():
    """미제출자는 score=0.00, 적절한 사유."""
    students = [{"sid": "2026300999", "name": "MISSING STUDENT"}]
    uploaders: set[str] = set()
    rows = build_score_rows("web2", students, uploaders, "10/6")
    r = rows[0]
    assert r[4] == "0.00"
    assert r[3] == "2"  # web2 = track 2


def test_build_score_rows_11col_structure():
    """build_score_rows가 정확히 11열을 생성하는지 검증."""
    students = [
        {"sid": "2026300111", "name": "AAA"},
        {"sid": "2026300222", "name": "BBB"},
    ]
    uploaders = {"AAA"}
    rows = build_score_rows("web1", students, uploaders, "10/6")
    for r in rows:
        assert len(r) == 11, f"행 길이가 11이 아닌 {len(r)}: {r}"


# ──────────────────────────────────────────────────────────────────────
# resolve_uploader 단위 테스트
# ──────────────────────────────────────────────────────────────────────


def test_resolve_uploader_alias():
    """별칭 매핑이 작동하는지 검증."""
    students = [{"sid": "001", "name": "BASTOLA KAMAL"}]
    assert resolve_uploader("Lotus Bastola", students) == "BASTOLA KAMAL"


def test_resolve_uploader_direct_match():
    """직접 이름 매칭 (단어 2개 이상 겹침)."""
    students = [{"sid": "001", "name": "NGUYEN THI CAM NGUYEN"}]
    result = resolve_uploader("Nguyễn Thị Cẩm Nguyên", students)
    # 별칭 매핑으로 먼저 해결됨
    assert result == "NGUYEN THI CAM NGUYEN"


def test_resolve_uploader_none():
    """매칭 실패 시 None 반환."""
    students = [{"sid": "001", "name": "BASTOLA KAMAL"}]
    assert resolve_uploader("Unknown Person", students) is None


# ──────────────────────────────────────────────────────────────────────
# upsert_grades_to_sheet 통합 테스트 (Mock)
# 사진 채점 행이 공통 upsert를 통해 13열로 안전하게 처리되는지 검증
# ──────────────────────────────────────────────────────────────────────


def test_photo_upsert_uses_13col_and_preserves_appeal():
    """사진 채점 행이 upsert_grades_to_sheet를 통해
    기존 행의 M열(이의제기)과 수식(E열/K열)을 보존하는지 검증."""
    from unittest.mock import MagicMock, patch

    fake_config = {
        "sheet_id": "fake_sheet_id",
        "target_gid": 12345,
    }

    mock_service = MagicMock()
    mock_service.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"sheetId": 12345, "title": "score"}}]
    }

    # 기존 시트에 (741, hw, 0.p)가 이미 존재하며 M열에 이의제기 내용이 있음
    existing_row = [
        "1",  # No
        1,  # wk
        "'741",  # ID
        "1",  # Track
        '=IF(H2="lab", IF(B2=3, ROUND((F2/9)*3, 2), ROUND((F2/10)*3, 2)), F2)',
        1.0,  # Score
        "hw",  # Type1
        "'0.p",  # Type2
        "Photo submitted to Google Photos album",  # Reason
        "09/15",  # Date
        '=IFERROR(VLOOKUP(C2, progress!$A$5:$C, 3, FALSE), "")',
        "'Google Photos Album",  # Subject
        "Reviewed and approved",  # Appeal Response (M열)
    ]
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [existing_row]
    }

    captured_updates = []

    def mock_update(spreadsheetId, range, valueInputOption, body):
        captured_updates.append((range, body.get("values", [])))
        return MagicMock(execute=MagicMock(return_value={"updates": {}}))

    mock_service.spreadsheets().values().update.side_effect = mock_update

    # 동일 키(741, hw, 0.p)로 점수 갱신 요청 (11열 입력)
    photo_rows = [
        [
            "",
            "1",
            "741",
            "1",
            "1.00",
            "hw",
            "0.p",
            "Photo submitted to Google Photos album",
            "10/6",
            "BASTOLA KAMAL",
            "Google Photos Album",
        ]
    ]

    from modules.sheet_updater import upsert_grades_to_sheet

    with patch(
        "modules.sheet_updater.load_course_config", return_value=fake_config
    ), patch(
        "modules.sheet_updater.get_sheet_service", return_value=mock_service
    ), patch(
        "modules.sheet_updater.sort_sheet_remote", return_value=True
    ), patch(
        "modules.sheet_updater.apply_score_sheet_formatting", return_value=None
    ):
        result = upsert_grades_to_sheet(photo_rows, course="web1")

    assert result is True
    assert len(captured_updates) == 1

    range_str, values = captured_updates[0]
    assert range_str == "score!A2:M2"
    updated_row = values[0]

    # 13열 검증
    assert len(updated_row) == 13

    # No 보존
    assert updated_row[0] == "1"

    # E열(인덱스 4): 기존 Scaled Score 수식 보존
    assert str(updated_row[4]).startswith("=")

    # K열(인덱스 10): VLOOKUP 수식 보존
    assert str(updated_row[10]).startswith("=")

    # M열(인덱스 12): 이의제기 결과 보존
    assert updated_row[12] == "Reviewed and approved"


def test_photo_upsert_new_row_gets_formulas():
    """신규 사진 행 추가 시 E열/K열 수식이 자동 생성되는지 검증."""
    from unittest.mock import MagicMock, patch

    fake_config = {
        "sheet_id": "fake_sheet_id",
        "target_gid": 12345,
    }

    mock_service = MagicMock()
    mock_service.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"sheetId": 12345, "title": "score"}}]
    }
    # 빈 시트
    mock_service.spreadsheets().values().get().execute.return_value = {"values": []}

    captured_appends = []

    def mock_append(spreadsheetId, range, valueInputOption, insertDataOption, body):
        captured_appends.append(body.get("values", []))
        return MagicMock(execute=MagicMock(return_value={"updates": {}}))

    mock_service.spreadsheets().values().append.side_effect = mock_append

    photo_rows = [
        [
            "",
            "1",
            "741",
            "1",
            "1.00",
            "hw",
            "0.p",
            "Photo submitted to Google Photos album",
            "10/6",
            "BASTOLA KAMAL",
            "Google Photos Album",
        ]
    ]

    from modules.sheet_updater import upsert_grades_to_sheet

    with patch(
        "modules.sheet_updater.load_course_config", return_value=fake_config
    ), patch(
        "modules.sheet_updater.get_sheet_service", return_value=mock_service
    ), patch(
        "modules.sheet_updater.sort_sheet_remote", return_value=True
    ), patch(
        "modules.sheet_updater.apply_score_sheet_formatting", return_value=None
    ):
        result = upsert_grades_to_sheet(photo_rows, course="web1")

    assert result is True
    assert len(captured_appends) == 1

    appended_row = captured_appends[0][0]
    assert len(appended_row) == 13

    # E열(인덱스 4): Scaled Score 수식 자동 생성
    assert str(appended_row[4]).startswith("=IF(")

    # K열(인덱스 10): Name VLOOKUP 수식 자동 생성
    assert str(appended_row[10]).startswith("=IFERROR(VLOOKUP(")

    # M열(인덱스 12): 빈 문자열
    assert appended_row[12] == ""

    # No(인덱스 0): 1부터 시작
    assert appended_row[0] == 1
