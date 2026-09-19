import re
from datetime import datetime
import email.utils


def parse_email_date(date_str):
    """
    이메일 헤더의 Date 문자열을 파싱하여 datetime 객체(로컬 시간 기준)로 반환합니다.
    """
    time_tuple = email.utils.parsedate_tz(date_str)
    if time_tuple:
        return datetime.fromtimestamp(email.utils.mktime_tz(time_tuple))
    return None


def grade_assignment(email_data, assignment_no, deadline_datetime=None):
    """
    개별 이메일 데이터를 기반으로 과제 0.4 기준의 3점 만점 채점을 수행합니다.
    """
    subject = email_data.get("subject", "")
    date_str = email_data.get("date_str", "")
    is_replied = email_data.get("is_replied_by_instructor", False)

    score = 0
    notes = []

    # 1. 제목 규칙 검증 (공백 허용, 대소문자 무시, 학번 8~9자리)
    pattern = rf"^\s*(과제|assignment|homework)\s*{re.escape(str(assignment_no))}\s*\d{{8,9}}\s*$"
    is_valid_title = bool(re.match(pattern, subject, re.IGNORECASE))

    if is_valid_title:
        score += 1
    else:
        notes.append("제목규칙위반")

    # 2. 마감 기한 검사
    is_on_time = True
    if deadline_datetime:
        mail_dt = parse_email_date(date_str)
        # 만약 파싱 불가하거나, 데드라인을 넘긴 경우 지각 처리
        if not mail_dt or mail_dt > deadline_datetime:
            is_on_time = False

    if is_on_time:
        score += 1
    else:
        notes.append("지각제출")

    # 3. 교수 피드백 (내가 지적사항을 회신한 적이 없으면 1점)
    if not is_replied:
        score += 1
    else:
        notes.append("지적사항회신있음")

    # 예외처리 - 이전 과제(예: 0.1, 0.2 등)의 경우 무조건 제출 시 1점이라면?
    # 요구사항 "이전 내용은 메일이 오기만 햇어도 1점 부여"
    is_old_assignment = False
    try:
        if float(assignment_no) < 0.4:
            is_old_assignment = True
    except ValueError:
        pass

    if is_old_assignment:
        # 이전 과제는 도착 확인만 되면 무조건 1점. (추가 가점 없음)
        score = 1
        notes = ["이전과제_도착1점"]

    return {
        "total_score": score,
        "type1": "hw",
        "type2": str(assignment_no),
        "details": {
            "title_ok": is_valid_title,
            "time_ok": is_on_time,
            "no_reply": not is_replied,
        },
        "reason": ", ".join(notes) if notes else "Pass (3/3)",
    }
