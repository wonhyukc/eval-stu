import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from bin.extract_emails import get_time_window, parse_students


def test_get_time_window():
    # 인자 없이 호출 시 폴백: start < deadline, 간격 7일 이내
    start_dt, deadline_dt = get_time_window()
    assert start_dt < deadline_dt

    # 주차 지정 시 deadline.md에서 읽어야 함
    start_dt4, deadline_dt4 = get_time_window("4")
    assert start_dt4 < deadline_dt4
    # 4주차 email deadline = 9/25 0:00 → start는 3주차 deadline(9/18 0:00)
    assert deadline_dt4.month == 9
    assert deadline_dt4.day == 25


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
