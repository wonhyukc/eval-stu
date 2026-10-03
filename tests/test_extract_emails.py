import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from bin.extract_emails import get_time_window, parse_students


def test_get_time_window():
    # 인자 없이 호출 시 폴백: start < deadline < grace, 간격 7일 이내
    start_dt, deadline_dt, grace_dt = get_time_window()
    assert start_dt < deadline_dt < grace_dt
    assert grace_dt == deadline_dt + timedelta(minutes=15)

    # 주차 지정 시 deadline.csv에서 읽어야 함
    start_dt4, deadline_dt4, grace_dt4 = get_time_window("4")
    assert start_dt4 < deadline_dt4 < grace_dt4
    # 4주차 email deadline = 9/25 0:00, grace = 9/25 0:15
    assert deadline_dt4.month == 9
    assert deadline_dt4.day == 25
    assert grace_dt4.minute == 15


def test_parse_students():
    # 파일이 존재하는 환경에서 실행될 경우 딕셔너리 반환 확인
    name_to_id, id_to_track, id_to_names = parse_students()

    assert isinstance(name_to_id, dict)
    assert isinstance(id_to_track, dict)

    # 만약 데이터가 파싱되었다면, key와 value가 모두 문자열이어야 함
    if len(id_to_track) > 0:
        for k, v in id_to_track.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
            assert k.isdigit()  # 학번은 숫자 형태
            assert v in {"1", "2", "4"}  # 트랙 번호는 1, 2, 4 로 정규화됨


def test_build_reply_body():
    from bin.extract_emails import build_reply_body

    id_to_names = {
        "2026300742": {"eng": "John Doe", "kor": "홍길동"},
        "2026300123": {"eng": "Jane Smith", "kor": "김철수"},
    }

    # K트랙 (4반) 테스트 -> 100% 한글
    row_py = {
        "학번": "2026300742",
        "track": "4",
        "점수": 1.0,
        "이유": "정상 제출 (기한내/정확한 양식)",
        "이름": "홍길동",
    }
    body_py = build_reply_body(row_py, "0.5", id_to_names)
    assert "안녕하세요 홍길동 학생" in body_py
    assert "0.5 과제 이메일이 정상적으로 접수 및 채점되었습니다" in body_py
    assert "정원혁 드림" in body_py

    # E트랙 (1반/2반) 테스트 -> 100% 영문
    row_web = {
        "학번": "2026300123",
        "track": "1",
        "점수": 1.0,
        "이유": "On-time & Exact Format",
        "이름": "Jane Smith",
    }
    body_web = build_reply_body(row_web, "0.5", id_to_names)
    assert "Dear Jane Smith" in body_web
    assert (
        "Your assignment submission has been received and graded successfully"
        in body_web
    )
    assert "Wonhyuk William Chung" in body_web


def test_print_grading_summary(capsys):
    from bin.extract_emails import print_grading_summary

    rows = [
        {"track": "4", "점수": 1.0, "is_replied": True},
        {"track": "1", "점수": 0.9, "is_replied": False},
        {"track": "2", "점수": 0.0, "is_replied": True},
    ]
    reply_stats = {
        "already_replied": 2,
        "newly_replied": 1,
        "unreplied": 0,
        "total_replied": 3,
        "total_submissions": 3,
    }
    print_grading_summary(rows, reply_stats=reply_stats)
    captured = capsys.readouterr().out
    assert "📊 [채점 결과 요약]" in captured
    assert "✉️ [답장 현황]" in captured
    assert "총 답장 건수   : 3건" in captured
    assert "이미 답장 완료 : 2건" in captured
    assert "이번에 답장 완료: 1건" in captured
