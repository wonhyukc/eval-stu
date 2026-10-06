import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import normalize_row_to_11cols, route_web_rows
from modules.grader import grade_assignment


def test_normalize_row_to_11cols_from_9cols():
    # 구 9열 구조: [no, sid, track, score, type, reason, date, name, subject]
    old_row = [
        1,
        "2026300123",
        "15144",
        1.0,
        "0.2",
        "On-time & Exact Format",
        "2026-09-15",
        "John Doe",
        "과제 0.2 2026300123",
    ]
    new_row = normalize_row_to_11cols(old_row)
    assert len(new_row) == 11
    # [No, wk, ID, Track, ScaledScore, Score, Type1, Type2, Reason, Date, Name]
    assert new_row[0] == 1  # No
    assert new_row[1] == "2"  # wk (0.2에서 추출)
    assert new_row[2] == "2026300123"  # ID
    assert new_row[3] == "15144"  # Track
    assert str(new_row[4]).startswith("=IF(")  # Scaled Score 수식 (E열)
    assert new_row[5] == 1.0  # Score 원점수 (F열)
    assert new_row[6] == "hw"  # Type1 (G열)
    assert new_row[7] == "0.2"  # Type2 (H열)
    assert new_row[8] == "On-time & Exact Format"  # Reason (I열)
    assert new_row[9] == "2026-09-15"  # Date (J열)
    assert str(new_row[10]).startswith("=IFERROR(")  # Name VLOOKUP 수식 (K열)


def test_normalize_row_to_11cols_from_old_11cols():
    # 구 11열 구조: [No, wk, ID, Track, Score, Type1, Type2, Reason, Date, Name, Subject]
    row_old_11 = [
        1,
        "1",
        "2026300999",
        "15143",
        1.0,
        "hw",
        "0.1",
        "Pass",
        "2026-09-10",
        "Alice",
        "Subject",
    ]
    result = normalize_row_to_11cols(row_old_11)
    assert len(result) == 11
    assert result[0] == 1  # No
    assert result[1] == "1"  # wk
    assert result[2] == "2026300999"  # ID
    assert result[3] == "15143"  # Track
    assert str(result[4]).startswith("=IF(")  # Scaled Score 수식
    assert result[5] == 1.0  # Score 원점수
    assert result[6] == "hw"  # Type1
    assert result[7] == "0.1"  # Type2
    assert result[8] == "Pass"  # Reason
    assert result[9] == "2026-09-10"  # Date
    assert str(result[10]).startswith("=IFERROR(")  # Name VLOOKUP 수식


def test_route_web_rows_11cols():
    # 11열 구조: Track은 인덱스 3
    web1_row = [
        1,
        "1",
        "2026300111",
        "15143",
        1.0,
        "hw",
        "0.1",
        "Pass",
        "2026-09-10",
        "Alice",
        "Subj1",
    ]
    web2_row = [
        2,
        "1",
        "2026300222",
        "15144",
        1.0,
        "hw",
        "0.1",
        "Pass",
        "2026-09-10",
        "Bob",
        "Subj2",
    ]

    r1, r2 = route_web_rows([web1_row, web2_row])
    assert len(r1) == 1
    assert r1[0][2] == "2026300111"
    assert len(r2) == 1
    assert r2[0][2] == "2026300222"


def test_grade_assignment_type_fields():
    email_data = {
        "subject": "과제 0.4 2026300123",
        "date_str": "Fri, 18 Sep 2026 12:00:00 +0900",
        "is_replied_by_instructor": False,
    }
    res = grade_assignment(email_data, "0.4")
    assert res["type1"] == "hw"
    assert res["type2"] == "0.4"


def test_sort_sheet_rows_4level():
    from modules.sheet_updater import sort_sheet_rows

    raw_data = [
        ["1", "2", "890", "1", "1", "hw", "0.2", "Pass", "9/10", "A", "S1"],
        ["2", "3", "742", "1", "1", "hw", "0.3", "Pass", "9/17", "B", "S2"],
        ["3", "3", "741", "1", "1", "hw", "0.3", "Pass", "9/17", "C", "S3"],
        ["4", "2", "741", "1", "1", "class", "", "Pass", "9/14", "D", "S4"],
    ]
    # 기본 동작: No 원본 유지
    sorted_default = sort_sheet_rows(raw_data)
    assert sorted_default[0][0] == "3"  # 3주차 741의 원래 No는 3
    assert sorted_default[1][0] == "2"  # 3주차 742의 원래 No는 2
    assert sorted_default[2][0] == "4"  # 2주차 class 741의 원래 No는 4
    assert sorted_default[3][0] == "1"  # 2주차 hw 890의 원래 No는 1

    # 명시적 renumber_desc=True인 경우만 재부여
    sorted_res = sort_sheet_rows(raw_data, renumber_desc=True)
    assert sorted_res[0][0] == "4"
    assert sorted_res[1][0] == "3"
    assert sorted_res[2][0] == "2"
    assert sorted_res[3][0] == "1"


@pytest.mark.parametrize("course", ["py", "web1", "web2"])
@pytest.mark.parametrize("input_width", [11, 13])
@pytest.mark.parametrize("renumber_desc", [False, True])
def test_sort_sheet_rows_formulas_follow_sorted_students(
    course, input_width, renumber_desc
):
    from copy import deepcopy
    from modules.sheet_updater import (
        make_name_vlookup_formula,
        make_scaled_score_formula,
        normalize_row_to_13cols,
        sort_sheet_rows,
    )

    rows = [
        [71, 2, "123", "1", 1.0, "hw", "0.2", "", "", "", "older"],
        [21, 3, "456", "1", 0.5, "hw", "0.3", "", "", "", "newer"],
    ]
    if input_width == 13:
        rows = [
            normalize_row_to_13cols(row, row_num=index, course=course)
            for index, row in enumerate(rows, start=2)
        ]
        rows[0][12] = "older appeal"
        rows[1][12] = "newer appeal"
    original = deepcopy(rows)

    result = sort_sheet_rows(rows, renumber_desc=renumber_desc, course=course)

    assert [row[2] for row in result] == ["456", "123"]
    assert [row[5] for row in result] == [0.5, 1.0]
    assert [row[11] for row in result] == ["newer", "older"]
    assert [row[0] for row in result] == (["2", "1"] if renumber_desc else [21, 71])
    assert [row[12] for row in result] == (
        ["newer appeal", "older appeal"] if input_width == 13 else ["", ""]
    )
    for row_num, row in enumerate(result, start=2):
        assert row[4] == make_scaled_score_formula(row_num)
        assert row[10] == make_name_vlookup_formula(row_num, course)
    assert rows == original


@pytest.mark.parametrize(
    "formula,offset,expected",
    [
        ("=ROUND(F2/$Z$1, 2)", 3, "=ROUND(F5/$Z$1, 2)"),
        ("=SUM($F3:F4)", -1, "=SUM($F2:F3)"),
        (
            '=IF(C2="F2", "C2 ""F2""", LOG10(F2))',
            1,
            '=IF(C3="F2", "C2 ""F2""", LOG10(F3))',
        ),
        ("='Q2'!F2+ABC2!$F$2", 1, "='Q2'!F3+ABC2!$F$2"),
    ],
)
def test_translate_formula_rows_preserves_fixed_references_and_literals(
    formula, offset, expected
):
    from modules.sheet_updater import _translate_formula_rows

    assert _translate_formula_rows(formula, offset) == expected


def test_sort_sheet_rows_preserves_custom_formulas():
    from modules.sheet_updater import normalize_row_to_13cols, sort_sheet_rows

    older = normalize_row_to_13cols(
        [71, 2, "123", "1", 1.0, "hw", "0.2", "", "", "", ""], row_num=2
    )
    newer = normalize_row_to_13cols(
        [21, 3, "456", "1", 0.5, "hw", "0.3", "", "", "", ""], row_num=3
    )
    older[4] = "=ROUND(F2/$Z$1, 2)"
    newer[4] = "=ROUND(F3/$Z$1, 2)"
    older[10] = '=IFERROR(VLOOKUP(C2, progress!$A$5:$C, 3, FALSE), "C2")'
    newer[10] = '=IFERROR(VLOOKUP(C3, progress!$A$5:$C, 3, FALSE), "C3")'

    result = sort_sheet_rows([older, newer])

    assert [row[2] for row in result] == ["456", "123"]
    assert result[0][4] == "=ROUND(F2/$Z$1, 2)"
    assert result[1][4] == "=ROUND(F3/$Z$1, 2)"
    assert result[0][10] == '=IFERROR(VLOOKUP(C2, progress!$A$5:$C, 3, FALSE), "C3")'
    assert result[1][10] == '=IFERROR(VLOOKUP(C3, progress!$A$5:$C, 3, FALSE), "C2")'
    assert older[4] == "=ROUND(F2/$Z$1, 2)"
    assert newer[4] == "=ROUND(F3/$Z$1, 2)"


def test_translate_reason_to_en():
    from modules.sheet_updater import translate_reason_to_en

    # 1. SSOT 표준 사유 매핑 검증 (2점 스케일 사유도 표준 영문으로 변환)
    assert (
        translate_reason_to_en("정확한 양식/조건충족(+2)") == "On-time & Exact Format"
    )

    # 2. 기타 표준 사유 매핑 검증
    assert (
        translate_reason_to_en("정상 제출 (기한내/정확한 양식)")
        == "On-time & Exact Format"
    )
    assert (
        translate_reason_to_en("경미한 양식 오차 (괄호/불필요 기호)")
        == "Minor format issue (Brackets/Extra text)"
    )
    assert (
        translate_reason_to_en("제목 학번 또는 과제명 누락")
        == "Missing Student ID or 0.x in Subject"
    )
    assert translate_reason_to_en("미제출") == "No submission"

    # 3. 복합 패턴 검증 (지각 및 위반)
    assert (
        translate_reason_to_en("지각 제출 (정확한 양식/조건충족(+2))")
        == "Late submission (On-time & Exact Format)"
    )
    assert (
        translate_reason_to_en("조건위반(첨부없음,제목양식오류)")
        == "Violation(No attachment,Title format error)"
    )


def test_translate_reason_to_ko():
    from modules.sheet_updater import translate_reason_to_ko

    # 1. 영문 -> 한글 매핑 검증
    assert (
        translate_reason_to_ko("On-time & Exact Format")
        == "정상 제출 (기한내/정확한 양식)"
    )
    assert (
        translate_reason_to_ko("Minor format issue (Brackets/Extra text)")
        == "경미한 양식 오차 (괄호/불필요 기호)"
    )
    assert (
        translate_reason_to_ko("Missing Student ID or 0.x in Subject")
        == "제목 학번 또는 과제명 누락"
    )
    assert translate_reason_to_ko("No submission") == "미제출"

    # 2. 복합 패턴 검증 (지각 및 위반)
    assert (
        translate_reason_to_ko("Late submission (On-time & Exact Format)")
        == "지각 제출 (정상 제출 (기한내/정확한 양식))"
    )
    assert (
        translate_reason_to_ko("Violation(No attachment,Title format error)")
        == "조건위반(첨부없음,제목양식오류)"
    )


def test_convert_score_to_1scale():
    from modules.sheet_updater import convert_score_to_1scale

    # 2점 스케일 → 1.0점 스케일 변환
    assert convert_score_to_1scale("2") == "1.0"
    assert convert_score_to_1scale("1.8") == "0.9"
    assert convert_score_to_1scale("1.5") == "0.5"
    assert convert_score_to_1scale("1.3") == "0.7"
    assert convert_score_to_1scale("0") == "0.0"
    assert convert_score_to_1scale("0.0") == "0.0"

    # 이미 1.0 스케일인 점수는 그대로
    assert convert_score_to_1scale("1.0") == "1.0"
    assert convert_score_to_1scale("0.9") == "0.9"
    assert convert_score_to_1scale("0.5") == "0.5"
    assert convert_score_to_1scale("0.7") == "0.7"


def test_normalize_reason_to_ssot():
    from modules.sheet_updater import normalize_reason_to_ssot

    # 2점 스케일 사유 → SSOT 표준 사유
    assert (
        normalize_reason_to_ssot("정확한 양식/조건충족(+2)")
        == "정상 제출 (기한내/정확한 양식)"
    )
    assert (
        normalize_reason_to_ssot("Met all conditions (+2)") == "On-time & Exact Format"
    )

    # 괄호 점수 제거 패턴
    assert "경미한 양식 오차" in normalize_reason_to_ssot(
        "조건위반(제목양식오류) (1.8)"
    )

    # 지각 사유 정규화
    assert (
        normalize_reason_to_ssot("지각 제출 (정확한 양식/조건충족(+2))")
        == "지각 제출 (다음 수업 시작 전)"
    )

    # 이미 SSOT 표준인 사유는 그대로
    assert (
        normalize_reason_to_ssot("정상 제출 (기한내/정확한 양식)")
        == "정상 제출 (기한내/정확한 양식)"
    )


def test_normalize_track():
    from modules.sheet_updater import normalize_track

    # 1반 매핑
    assert normalize_track("1") == "1"
    assert normalize_track("01") == "1"
    assert normalize_track("15143") == "1"
    assert normalize_track("761") == "1"
    assert normalize_track("web1") == "1"
    assert normalize_track("웹1") == "1"

    # 2반 매핑
    assert normalize_track("2") == "2"
    assert normalize_track("02") == "2"
    assert normalize_track("15144") == "2"
    assert normalize_track("762") == "2"
    assert normalize_track("web2") == "2"

    # 4반 매핑
    assert normalize_track("4") == "4"
    assert normalize_track("04") == "4"
    assert normalize_track("14712") == "4"
    assert normalize_track("468") == "4"
    assert normalize_track("python") == "4"
    assert normalize_track("파이썬") == "4"


def test_convert_lab_score_to_3scale():
    from modules.sheet_updater import convert_lab_score_to_3scale

    # 10점 만점 기준
    assert convert_lab_score_to_3scale(10, max_score=10) == "3.0"
    assert convert_lab_score_to_3scale(5, max_score=10) == "1.5"
    assert convert_lab_score_to_3scale(0, max_score=10) == "0.0"

    # 9점 만점 기준 (3주차 실습 L3)
    assert convert_lab_score_to_3scale(9, max_score=9) == "3.0"
    assert convert_lab_score_to_3scale(6, max_score=9) == "2.0"

    # 11점 만점 기준 (5/7주차 실습)
    assert convert_lab_score_to_3scale(11, max_score=11) == "3.0"

    # 13점 만점 기준 (6주차 실습)
    assert convert_lab_score_to_3scale(13, max_score=13) == "3.0"

    # 문자열 분수 지원 ("9/10", "10/10")
    assert convert_lab_score_to_3scale("9/10") == "2.7"
    assert convert_lab_score_to_3scale("10/10") == "3.0"

    # 이미 3.0 스케일인 경우 (denom <= 3.0)
    assert convert_lab_score_to_3scale("3.0", max_score=3.0) == "3.0"
    assert convert_lab_score_to_3scale("2.5", max_score=3.0) == "2.5"


def test_format_date_to_mmdd_hhmm():
    from modules.sheet_updater import format_date_to_mmdd_hhmm

    # Gmail 영문 형태
    assert format_date_to_mmdd_hhmm("Wed, Sep 30, 2026, 8:15 PM") == "09/30 20:15"
    assert format_date_to_mmdd_hhmm("Thu, Oct 1, 2026, 12:08 AM") == "10/01 00:08"
    assert format_date_to_mmdd_hhmm("Thu, Oct 1, 2026, 12:38 PM") == "10/01 12:38"
    assert format_date_to_mmdd_hhmm("Fri, Oct 2, 2026, 11:02 AM") == "10/02 11:02"

    # 이미 mm/dd hh:mm 형태
    assert format_date_to_mmdd_hhmm("09/30 20:15") == "09/30 20:15"
    assert format_date_to_mmdd_hhmm("9/30 8:15") == "09/30 08:15"

    # 한국어 형태
    assert format_date_to_mmdd_hhmm("2026. 10. 1. 오후 8:15") == "10/01 20:15"

    # 월/일 형태
    assert format_date_to_mmdd_hhmm("9/25") == "09/25"
    assert format_date_to_mmdd_hhmm("09/25") == "09/25"


def test_make_scaled_score_formula():
    from modules.sheet_updater import make_scaled_score_formula

    formula_172 = make_scaled_score_formula(172)
    assert (
        formula_172
        == '=IF(H172="lab", IF(B172=3, ROUND((F172/9)*3, 2), ROUND((F172/10)*3, 2)), F172)'
    )

    formula_193 = make_scaled_score_formula(193)
    assert (
        formula_193
        == '=IF(H193="lab", IF(B193=3, ROUND((F193/9)*3, 2), ROUND((F193/10)*3, 2)), F193)'
    )


def test_make_name_vlookup_formula():
    from modules.sheet_updater import make_name_vlookup_formula

    formula_web = make_name_vlookup_formula(50, course="web1")
    assert formula_web == '=IFERROR(VLOOKUP(C50, progress!$A$5:$C, 3, FALSE), "")'

    formula_py = make_name_vlookup_formula(50, course="py")
    assert formula_py == '=IFERROR(VLOOKUP(C50, progress!$A$5:$B, 2, FALSE), "")'


def test_normalize_row_to_13cols():
    from modules.sheet_updater import normalize_row_to_13cols

    # 11열 입력: [no, wk, sid, track, score, t1, t2, reason, dt, name, subj]
    row_11 = [
        1,
        "3",
        "2026300123",
        "1",
        10.0,
        "hw",
        "lab",
        "정상 제출",
        "09/30 10:00",
        "홍길동",
        "과제제출",
    ]
    row_13 = normalize_row_to_13cols(row_11, row_num=10, course="web1")
    assert len(row_13) == 13
    assert row_13[0] == 1  # No
    assert row_13[1] == "3"  # wk
    assert row_13[2] == "2026300123"  # ID
    assert row_13[3] == "1"  # Track
    assert row_13[4].startswith("=IF(H10=")  # Scaled Score 수식 (E열)
    assert row_13[5] == 10.0  # Score 원점수 (F열)
    assert row_13[6] == "hw"  # Type1 (G열)
    assert row_13[7] == "lab"  # Type2 (H열)
    assert row_13[8] == "정상 제출"  # Reason (I열)
    assert row_13[9] == "09/30 10:00"  # Date (J열)
    assert (
        row_13[10] == '=IFERROR(VLOOKUP(C10, progress!$A$5:$C, 3, FALSE), "")'
    )  # Name (K열)
    assert row_13[11] == "과제제출"  # Subject (L열)
    assert row_13[12] == ""  # Appeal (M열)


@pytest.mark.parametrize("input_width", [6, 7, 8, 9, 10, 11])
@pytest.mark.parametrize("score,type2", [(0.5, "0.2"), (0, "0.2"), (9, "lab")])
def test_normalize_row_to_13cols_preserves_short_legacy_rows(input_width, score, type2):
    from modules.sheet_updater import (
        make_name_vlookup_formula,
        make_scaled_score_formula,
        normalize_row_to_13cols,
    )

    full_row = [71, 2, "123", "1", score, "hw", type2, "", "", "", ""]
    short_row = full_row[:input_width]

    result = normalize_row_to_13cols(short_row, row_num=7, course="py")

    assert result == [
        71,
        2,
        "123",
        "1",
        make_scaled_score_formula(7),
        score,
        "hw",
        type2 if input_width > 6 else "",
        "",
        "",
        make_name_vlookup_formula(7, "py"),
        "",
        "",
    ]
    assert short_row == full_row[:input_width]


@pytest.mark.parametrize(
    "function_name", ["append_grades_to_sheet", "upsert_grades_to_sheet"]
)
def test_upload_short_legacy_row_preserves_score_and_types(function_name):
    from unittest.mock import MagicMock, patch
    from modules import sheet_updater

    service = MagicMock()
    service.spreadsheets().values().get().execute.return_value = {"values": []}
    row = [0, 2, "123", "1", 0.5, "hw", "0.2", "Pass", "10/01 10:00"]

    with patch.object(
        sheet_updater,
        "load_course_config",
        return_value={"sheet_id": "fake", "target_gid": 1},
    ), patch.object(
        sheet_updater, "get_sheet_service", return_value=service
    ), patch.object(
        sheet_updater, "get_target_sheet_title", return_value="score"
    ), patch.object(
        sheet_updater, "get_max_no", return_value=0
    ), patch.object(
        sheet_updater, "apply_score_sheet_formatting"
    ), patch.object(
        sheet_updater, "sort_sheet_remote", return_value=True
    ):
        assert getattr(sheet_updater, function_name)([row], course="web1")

    written = (
        service.spreadsheets().values().append.call_args.kwargs["body"]["values"][0]
    )
    assert written[2] == "'123"
    assert written[5:8] == [0.5, "hw", "'0.2"]
    assert written[8:10] == ["Pass", "10/01 10:00"]
    assert row == [0, 2, "123", "1", 0.5, "hw", "0.2", "Pass", "10/01 10:00"]


def test_is_lab_assignment():
    from modules.sheet_updater import is_lab_assignment

    # 1. 표준 실습 표기
    assert is_lab_assignment("hw", "lab") is True
    assert is_lab_assignment("hw", "LAB") is True
    assert is_lab_assignment("hw", "실습") is True
    assert is_lab_assignment("lab", "3") is True
    assert is_lab_assignment("실습", "3") is True

    # 2. 작은따옴표 접두 표기 (시트 포맷팅 후 형태)
    assert is_lab_assignment("hw", "'lab") is True
    assert is_lab_assignment("hw", "'LAB") is True
    assert is_lab_assignment("hw", "'실습") is True
    assert is_lab_assignment("hw", "'L3") is True
    assert is_lab_assignment("hw", "'l4") is True

    # 3. 주차별 실습 표기 (L3, L4, L5 등)
    assert is_lab_assignment("hw", "L3") is True
    assert is_lab_assignment("hw", "l3") is True
    assert is_lab_assignment("hw", "L10") is True

    # 4. 이메일 과제 및 일반 과제 (False)
    assert is_lab_assignment("hw", "0.1") is False
    assert is_lab_assignment("hw", "'0.1") is False
    assert is_lab_assignment("hw", "0.4") is False
    assert is_lab_assignment("hw", "'0.4") is False
    assert is_lab_assignment("class", "att") is False
    assert is_lab_assignment("", "") is False
    assert is_lab_assignment(None, None) is False


def test_upsert_grades_to_sheet_preserves_lab_raw_scores():
    from unittest.mock import MagicMock, patch
    from modules.sheet_updater import upsert_grades_to_sheet

    fake_config = {
        "sheet_id": "fake_sheet_id",
        "target_gid": 12345,
    }

    mock_service = MagicMock()
    mock_service.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"sheetId": 12345, "title": "score"}}]
    }
    mock_service.spreadsheets().values().get().execute.return_value = {"values": []}

    captured_appends = []

    def mock_append(spreadsheetId, range, valueInputOption, insertDataOption, body):
        captured_appends.append(body.get("values", []))
        return MagicMock(execute=MagicMock(return_value={"updates": {}}))

    mock_service.spreadsheets().values().append.side_effect = mock_append

    test_rows = [
        [
            1,
            "3",
            "2026300123",
            "1",
            10,
            "hw",
            "lab",
            "정상제출",
            "09/30 10:00",
            "홍길동",
            "실습",
        ],
        [
            2,
            "3",
            "2026300456",
            "1",
            9,
            "hw",
            "L3",
            "정상제출",
            "09/30 10:00",
            "김철수",
            "실습",
        ],
    ]

    with patch(
        "modules.sheet_updater.load_course_config", return_value=fake_config
    ), patch(
        "modules.sheet_updater.get_sheet_service", return_value=mock_service
    ), patch(
        "modules.sheet_updater.sort_sheet_remote", return_value=True
    ), patch(
        "modules.sheet_updater.apply_score_sheet_formatting", return_value=None
    ):
        result = upsert_grades_to_sheet(test_rows, course="web1")

    assert result is True
    assert len(captured_appends) == 1
    appended_rows = captured_appends[0]
    assert len(appended_rows) == 2
    # 13열 구조 검증:
    # E열(인덱스 4)은 Scaled Score 수식
    assert appended_rows[0][4].startswith("=IF(")
    # F열(인덱스 5)은 원점수(10.0, 9.0)가 반토막 나지 않고 유지됨
    assert appended_rows[0][5] == 10.0
    assert appended_rows[1][5] == 9.0
    # K열(인덱스 10)은 VLOOKUP 수식
    assert appended_rows[0][10].startswith("=IFERROR(VLOOKUP(")


def test_upsert_grades_to_sheet_formula_preservation():
    """기존 행 업데이트 시 E열 수식 및 K열 Name VLOOKUP 수식이 보존되는지 검증."""
    from unittest.mock import MagicMock, patch
    from modules.sheet_updater import upsert_grades_to_sheet

    fake_config = {
        "sheet_id": "fake_sheet_id",
        "target_gid": 12345,
    }

    mock_service = MagicMock()
    mock_service.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"sheetId": 12345, "title": "score"}}]
    }
    # 기존 시트에 이미 1행이 있는 상태 (2행에 13열 데이터, 수식 포함)
    existing_row = [
        "1",
        2,
        "'123",
        "1",
        '=IF(H2="lab", IF(B2=3, ROUND((F2/9)*3, 2), ROUND((F2/10)*3, 2)), F2)',
        1.0,
        "hw",
        "'0.2",
        "On-time & Exact Format",
        "09/15 14:00",
        '=IFERROR(VLOOKUP(C2, progress!$A$5:$C, 3, FALSE), "")',
        "과제 0.2",
        "",
    ]
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [existing_row]
    }

    captured_updates = []

    def mock_update(spreadsheetId, range, valueInputOption, body):
        captured_updates.append((range, body.get("values", [])))
        return MagicMock(execute=MagicMock(return_value={"updates": {}}))

    mock_service.spreadsheets().values().update.side_effect = mock_update

    # 동일한 키('123', 'hw', '0.2')로 점수 및 사유 변경 요청
    test_update = [
        [
            1,
            "2",
            "2026300123",
            "1",
            0.9,
            "hw",
            "0.2",
            "경미한 양식 오차 (괄호/불필요 기호)",
            "09/15 14:00",
            "홍길동",
            "과제 0.2",
        ]
    ]

    with patch(
        "modules.sheet_updater.load_course_config", return_value=fake_config
    ), patch(
        "modules.sheet_updater.get_sheet_service", return_value=mock_service
    ), patch(
        "modules.sheet_updater.sort_sheet_remote", return_value=True
    ), patch(
        "modules.sheet_updater.apply_score_sheet_formatting", return_value=None
    ):
        result = upsert_grades_to_sheet(test_update, course="web1")

    assert result is True
    assert len(captured_updates) == 1
    range_str, values = captured_updates[0]
    assert range_str == "score!A2:M2"
    updated_row = values[0]
    # E열(인덱스 4)과 K열(인덱스 10)의 수식이 보존되었는지 검증!
    assert updated_row[4] == existing_row[4]
    assert updated_row[5] == 0.9  # 원점수 업데이트
    assert updated_row[10] == existing_row[10]  # VLOOKUP 보존


def test_append_grades_to_sheet_preserves_lab_raw_scores():
    from unittest.mock import MagicMock, patch
    from modules.sheet_updater import append_grades_to_sheet

    fake_config = {
        "sheet_id": "fake_sheet_id",
        "target_gid": 12345,
    }

    mock_service = MagicMock()
    mock_service.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"sheetId": 12345, "title": "score"}}]
    }
    mock_service.spreadsheets().values().get().execute.return_value = {"values": []}

    captured_appends = []

    def mock_append(spreadsheetId, range, valueInputOption, insertDataOption, body):
        captured_appends.append(body.get("values", []))
        return MagicMock(execute=MagicMock(return_value={"updates": {}}))

    mock_service.spreadsheets().values().append.side_effect = mock_append

    test_rows = [
        [
            1,
            "3",
            "2026300123",
            "1",
            10,
            "hw",
            "lab",
            "정상제출",
            "09/30 10:00",
            "홍길동",
            "실습",
        ],
        [
            2,
            "3",
            "2026300456",
            "1",
            9,
            "hw",
            "'L3",
            "정상제출",
            "09/30 10:00",
            "김철수",
            "실습",
        ],
    ]

    with patch(
        "modules.sheet_updater.load_course_config", return_value=fake_config
    ), patch("modules.sheet_updater.get_sheet_service", return_value=mock_service):
        result = append_grades_to_sheet(test_rows, course="web1")

    assert result is True
    assert len(captured_appends) == 1
    appended_rows = captured_appends[0]
    assert len(appended_rows) == 2
    # 13열 구조: E열=수식, F열=원점수(10.0, 9.0), K열=VLOOKUP
    assert appended_rows[0][4].startswith("=IF(")
    assert appended_rows[0][5] == 10.0
    assert appended_rows[1][5] == 9.0
    assert appended_rows[0][10].startswith("=IFERROR(")
