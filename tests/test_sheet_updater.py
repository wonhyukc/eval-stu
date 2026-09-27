import os
import sys

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
    # [No, wk, ID, Track, Score, Type1, Type2, Reason, Date, Name, Subject]
    assert new_row[0] == 1  # No
    assert new_row[1] == "2"  # wk (0.2에서 추출)
    assert new_row[2] == "2026300123"  # ID
    assert new_row[3] == "15144"  # Track
    assert new_row[4] == 1.0  # Score
    assert new_row[5] == "hw"  # Type1
    assert new_row[6] == "0.2"  # Type2
    assert new_row[7] == "On-time & Exact Format"  # Reason
    assert new_row[8] == "2026-09-15"  # Date
    assert new_row[9] == "John Doe"  # Name
    assert new_row[10] == "과제 0.2 2026300123"  # Subject


def test_normalize_row_to_11cols_already_11cols():
    row_11 = [
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
    result = normalize_row_to_11cols(row_11)
    assert result == row_11


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
    sorted_res = sort_sheet_rows(raw_data, renumber_desc=True)

    # 1. 3주차가 2주차보다 위
    assert sorted_res[0][1] == "3"
    assert sorted_res[1][1] == "3"
    assert sorted_res[2][1] == "2"
    assert sorted_res[3][1] == "2"

    # 2. 3주차 내에서 741이 742보다 위 (학번 오름차순)
    assert sorted_res[0][2] == "741"
    assert sorted_res[1][2] == "742"

    # 3. 2주차 내에서 class가 hw보다 위 (Type1 오름차순)
    assert sorted_res[2][5] == "class"
    assert sorted_res[3][5] == "hw"

    # 4. No 번호가 내림차순(4 down to 1)으로 재부여
    assert sorted_res[0][0] == "4"
    assert sorted_res[1][0] == "3"
    assert sorted_res[2][0] == "2"
    assert sorted_res[3][0] == "1"


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
