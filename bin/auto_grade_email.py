#!/home/hyuk/prj/stu/eval-stu/.venv/bin/python3
# mypy: ignore-errors
"""auto_grade_email.py — 이메일 과제 자동 채점·시트 동기화·답장 발송 스크립트

사용법:
  python bin/auto_grade_email.py                  # 현재 주차 자동 탐지
  python bin/auto_grade_email.py --task 0.3        # 특정 과제 번호 지정
  python bin/auto_grade_email.py --grace web1      # 월 16:00 grace-period 마감 처리
  python bin/auto_grade_email.py --dry-run         # 시트/답장 없이 채점만 미리보기

실행 주기 (systemd timer):
  - 금·토·일·월 08:00  → 전체 채점 + 답장
  - 월 09:00           → 4반(py) grace-period 마감 처리
  - 월 13:00           → 2반(web2) grace-period 마감 처리
  - 월 16:00           → 1반(web1) grace-period 마감 처리
"""

import argparse
import logging
import os
import re
import subprocess
import sys
import time
import email.utils
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ playwright가 설치되지 않았습니다: pip install playwright")
    sys.exit(1)

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from modules.sheet_updater import upsert_grades_to_sheet

# ── 상수 ──────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))
SEMESTER_START = datetime(2026, 8, 31, 0, 0, 0, tzinfo=KST)  # wk1 시작
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 과목별 지각 마감 시각 (다음 수업 시작 전)
LATE_CUTOFF_HOURS = {
    "4": 9,  # 월 09:00
    "2": 13,  # 월 13:00
    "1": 16,  # 월 16:00
}


def setup_logging(task_id: str) -> logging.Logger:
    """로그 파일 + 콘솔 동시 출력 설정."""
    now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"grade_{task_id}_{now_str}.log"
    logger = logging.getLogger("auto_grade")
    logger.setLevel(logging.INFO)
    # 파일 핸들러
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    # 콘솔 핸들러
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)
    logger.info(f"📝 로그 파일: {log_file}")
    return logger


def calculate_current_task() -> str:
    """현재 날짜 기준으로 과제 번호(0.x) 자동 계산.
    학기 시작: 2026-08-31 (wk1). 실행 시점의 직전 목요일이 마감인 주차.
    """
    now = datetime.now(KST)
    # 직전 목요일 찾기 (목=3)
    days_since_thu = (now.weekday() - 3) % 7
    if days_since_thu == 0 and now.hour < 24:
        days_since_thu = 0  # 목요일 당일은 이번 주 마감
    last_thu = now - timedelta(days=days_since_thu)
    # 주차 계산: 학기 시작일부터 몇 번째 주인지
    delta = last_thu - SEMESTER_START
    wk = max(1, delta.days // 7 + 1)
    task_id = f"0.{wk}"
    return task_id


def get_deadline_dt(task_id: str) -> datetime:
    """과제 번호로부터 마감 시각 계산 (목 23:59 + 15분 유예 = 금 00:15 KST)."""
    wk_num = int(task_id.split(".")[1])
    # wk1 시작 = 2026-08-31 (월), 해당 주의 목요일 = +3일
    wk_start = SEMESTER_START + timedelta(weeks=wk_num - 1)
    thu = wk_start + timedelta(days=3)  # 목요일
    deadline = thu.replace(hour=23, minute=59, second=0) + timedelta(minutes=16)
    return deadline


def get_late_cutoff_dt(task_id: str, track: str) -> datetime:
    """트랙별 지각 마감 시각 (다음 월요일 수업 시작 시각)."""
    wk_num = int(task_id.split(".")[1])
    wk_start = SEMESTER_START + timedelta(weeks=wk_num - 1)
    next_mon = wk_start + timedelta(days=7)  # 다음 주 월요일
    hour = LATE_CUTOFF_HOURS.get(track, 16)
    return next_mon.replace(hour=hour, minute=0, second=0)


def parse_students():
    """SSOT 수강생 명단 로드."""
    students_by_id = {}
    name_to_id = {}
    email_to_id = {}

    py_path = BASE_DIR / "5input/students/py-students.md"
    if py_path.exists():
        with open(py_path, "r", encoding="utf-8") as f:
            for line in f:
                cols = [c.strip() for c in line.split("|")]
                if len(cols) > 8 and cols[3].isdigit():
                    sid = cols[3]
                    students_by_id[sid] = {
                        "id": sid,
                        "track": "4",
                        "course_id": cols[1],
                        "dept": cols[2],
                        "eng_name": cols[4],
                        "email": cols[5].lower(),
                        "phone": cols[6],
                        "nat": cols[7],
                        "kor_name": cols[8],
                    }
                    clean_eng = re.sub(r"\s+", "", cols[4]).lower()
                    if clean_eng:
                        name_to_id[clean_eng] = sid
                    clean_kor = re.sub(r"\s+", "", cols[8])
                    if clean_kor:
                        name_to_id[clean_kor] = sid
                    email_to_id[cols[5].lower()] = sid

    wb_path = BASE_DIR / "5input/students/wb-students.md"
    if wb_path.exists():
        with open(wb_path, "r", encoding="utf-8") as f:
            for line in f:
                cols = [c.strip() for c in line.split("|")]
                if len(cols) > 8 and cols[3].isdigit():
                    sid = cols[3]
                    trk = (
                        "1"
                        if cols[1] == "15143"
                        else "2" if cols[1] == "15144" else cols[1]
                    )
                    students_by_id[sid] = {
                        "id": sid,
                        "track": trk,
                        "course_id": cols[1],
                        "dept": cols[2],
                        "eng_name": cols[4],
                        "email": cols[5].lower(),
                        "phone": cols[6],
                        "nat": cols[7],
                        "kor_name": cols[8],
                    }
                    clean_eng = re.sub(r"\s+", "", cols[4]).lower()
                    if clean_eng:
                        name_to_id[clean_eng] = sid
                    clean_kor = re.sub(r"\s+", "", cols[8])
                    if clean_kor:
                        name_to_id[clean_kor] = sid
                    email_to_id[cols[5].lower()] = sid

    return students_by_id, name_to_id, email_to_id


def parse_gmail_date(
    date_str: str, log: logging.Logger | None = None
) -> datetime | None:
    """Gmail 타임스탬프 문자열을 KST datetime으로 안전하게 파싱한다.

    Gmail 웹 UI 언어 설정(영어, 한국어 등) 및 타임존 누락 형태를 모두 처리한다.
    UI에 표시되는 시각은 이미 사용자 로컬(KST) 기준이므로 tzinfo가 없으면 KST로 처리한다.
    """
    if not date_str or not date_str.strip():
        return None
    raw = date_str.strip()

    # 1차 시도: email.utils (RFC 2822 / 표준 날짜 형식)
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        else:
            dt = dt.astimezone(KST)
        return dt
    except Exception:
        pass

    # 2차 시도: dateutil.parser (영어 구문 e.g. 'Sep 28, 2026, 9:20 AM')
    try:
        import dateutil.parser

        dt = dateutil.parser.parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        else:
            dt = dt.astimezone(KST)
        return dt
    except Exception:
        pass

    # 3차 시도: 한국어 Gmail 포맷 (e.g. '2026년 9월 28일 (일) 오전 9:20' 또는 '9월 28일 (일) 오후 3:11')
    m_kor = re.search(
        r"(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일.*?((?:오전|오후)\s*\d{1,2}:\d{2})",
        raw,
    )
    if m_kor:
        try:
            year = int(m_kor.group(1)) if m_kor.group(1) else datetime.now(KST).year
            month = int(m_kor.group(2))
            day = int(m_kor.group(3))
            time_part = m_kor.group(4)
            is_pm = "오후" in time_part
            t_match = re.search(r"(\d{1,2}):(\d{2})", time_part)
            if t_match:
                hour = int(t_match.group(1))
                minute = int(t_match.group(2))
                if is_pm and hour < 12:
                    hour += 12
                elif not is_pm and hour == 12:
                    hour = 0
                return datetime(year, month, day, hour, minute, 0, tzinfo=KST)
        except Exception:
            pass

    if log:
        log.warning(f"   ⚠️ 날짜 파싱 실패: '{raw}'")
    return None


def evaluate_submission(
    subject: str,
    body_text: str,
    student_info: dict | None,
    email_dt: datetime | None,
    task_id: str,
    log: logging.Logger | None = None,
) -> tuple[float, str, str, str]:
    """채점 로직 (1docs/score-email.md SSOT 준수)."""
    # 1. 순수 본문 검증
    body_lines = body_text.splitlines()
    pure_lines = []
    for line in body_lines:
        s = line.strip()
        if (
            s.startswith(">")
            or s.startswith("wrote:")
            or "đã viết:" in s
            or "작성:" in s
        ):
            continue
        pure_lines.append(s)
    pure_body = "\n".join(pure_lines).strip()
    pure_len = len(re.sub(r"\s+", "", pure_body))
    has_url = bool(re.search(r"https?://\S+", pure_body))

    if pure_len < 30 and not has_url:
        if log:
            log.info(
                f"   [채점판정] 본문 미달 (순수길이: {pure_len}자, URL: {has_url}) → 0.0점"
            )
        return (
            0.0,
            "Empty Body / Quoted Text Only",
            "본문 미작성(단순 회신)",
            f"Pure body too short ({pure_len} chars) & no URL",
        )

    # 2. 기한 확인
    track = student_info["track"] if student_info else "1"
    deadline_dt = get_deadline_dt(task_id)
    late_cutoff_dt = get_late_cutoff_dt(task_id, track)
    is_late = False

    if email_dt:
        if log:
            log.info(
                f"   [기한검사] 발송시각: {email_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
                f"정규마감: {deadline_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
                f"지각마감: {late_cutoff_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
        if email_dt > late_cutoff_dt:
            if log:
                log.info(
                    f"   [채점판정] 지각마감초과 ({email_dt} > {late_cutoff_dt}) → 0.0점"
                )
            return (
                0.0,
                "Rejected (Past late cutoff)",
                "불인정 (지각 마감 초과)",
                f"Submitted after late cutoff ({late_cutoff_dt})",
            )
        if email_dt > deadline_dt:
            is_late = True
            if log:
                log.info(
                    f"   [채점판정] 정규마감초과 ({email_dt} > {deadline_dt}) → 지각 대상"
                )
        else:
            if log:
                log.info(f"   [채점판정] 정규기한내제출 ({email_dt} <= {deadline_dt})")
    else:
        if log:
            log.warning("   [기한검사] email_dt 없음(파싱실패 등) → 정시 기준으로 처리")

    # 3. 제목 검사
    clean_sub = re.sub(
        r"^(\s*re:\s*|\s*fwd:\s*)+", "", subject, flags=re.IGNORECASE
    ).strip()
    clean_sub_nospace = re.sub(r"\s+", "", clean_sub).lower()
    sid = student_info["id"] if student_info else ""
    task_num = task_id  # e.g. "0.3"

    # 정확한 형식: (과제|assignment)\s*0\.x\s*10자리학번
    exact_pattern = rf"^(과제|assignment)\s*{re.escape(task_num)}\s*{sid}$"
    is_exact = bool(re.match(exact_pattern, clean_sub, re.IGNORECASE))

    has_task = task_num in clean_sub_nospace
    has_id = (sid in clean_sub) or bool(re.search(r"2026\d{6}", clean_sub))

    if not is_late:
        if is_exact:
            return (
                1.0,
                "On-time & Exact Format",
                "정상 제출 (기한내/정확한 양식)",
                "Exact format",
            )
        elif has_task and has_id:
            return (
                0.9,
                "Minor format issue (Brackets/Extra text)",
                "경미한 양식 오차 (괄호/불필요 기호)",
                "Brackets, labels or extra text",
            )
        else:
            return (
                0.7,
                "Missing Student ID or 0.x in Subject",
                "제목 학번 또는 과제명 누락",
                "Missing ID or assignment number",
            )
    else:
        if has_id and has_task:
            return (
                0.5,
                "Late submission (Before next class)",
                "지각 제출 (다음 수업 시작 전)",
                "Late but ID present",
            )
        else:
            return (
                0.2,
                "Late & Format Issue (Missing ID)",
                "지각 + 제목 학번 누락",
                "Late & format issue",
            )


def build_reply_body(item: dict, task_id: str) -> str:
    """트랙별 언어 정책 및 실제 채점 사유에 맞는 답장 본문 생성."""
    s_info = item["student_info"]
    score = item["score"]
    track = s_info["track"]

    if track == "4":
        # K트랙 100% 한글
        name = s_info.get("kor_name") or s_info["eng_name"]
        if score >= 0.9:
            return (
                f"안녕하세요 {name} 학생,\n\n"
                f"{task_id} 과제 이메일이 정상적으로 접수 및 채점되었습니다.\n"
                f"- 과제: {task_id}\n"
                f"- 점수: {score:.1f} / 1.0\n"
                f"- 상태: {item['reason_ko']}\n\n"
                f"수고 많으셨습니다.\n"
                f"정원혁 드림"
            )
        elif score > 0.0:
            return (
                f"안녕하세요 {name} 학생,\n\n"
                f"제출하신 {task_id} 과제 이메일을 확인하였습니다.\n"
                f"- 과제: {task_id}\n"
                f"- 점수: {score:.1f} / 1.0\n"
                f"- 사유: {item['reason_ko']}\n\n"
                f"규정에 맞춰 다음 과제 제출 시 유의해 주시기 바랍니다.\n"
                f"정원혁 드림"
            )
        else:
            # 0.0점: 실제 사유(지각 마감 초과 vs 본문 누락) 반영
            if "마감 초과" in item["reason_ko"]:
                return (
                    f"안녕하세요 {name} 학생,\n\n"
                    f"제출하신 {task_id} 과제 이메일이 지각 마감 시한(수업 시작 시각) 이후에 도착하여 정상 채점되지 않았습니다 (0.0점).\n"
                    f"- 과제: {task_id}\n"
                    f"- 점수: {score:.1f} / 1.0\n"
                    f"- 사유: {item['reason_ko']}\n\n"
                    f"정원혁 드림"
                )
            else:
                return (
                    f"안녕하세요 {name} 학생,\n\n"
                    f"제출하신 이메일의 본문 내용이 확인되지 않아 정상 채점되지 않았습니다 (0.0점).\n"
                    f"- 과제: {task_id}\n"
                    f"- 점수: {score:.1f} / 1.0\n"
                    f"- 사유: {item['reason_ko']}\n\n"
                    f"과제 내용 및 결과를 본문에 포함하여 다시 제출해 주시기 바랍니다.\n\n"
                    f"정원혁 드림"
                )
    else:
        # E트랙 100% 영문
        name = s_info["eng_name"]
        if score >= 0.9:
            return (
                f"Dear {name},\n\n"
                f"Your assignment submission has been received and graded successfully.\n"
                f"- Task: {task_id}\n"
                f"- Score: {score:.1f} / 1.0\n"
                f"- Status: {item['reason_en']}\n\n"
                f"Thank you for your submission.\n"
                f"Best regards,\n"
                f"Wonhyuk William Chung"
            )
        elif score > 0.0:
            return (
                f"Dear {name},\n\n"
                f"Your assignment submission has been reviewed:\n"
                f"- Task: {task_id}\n"
                f"- Score: {score:.1f} / 1.0\n"
                f"- Note: {item['reason_en']}\n\n"
                f"Please make sure to follow the required format and deadline for future assignments.\n"
                f"Best regards,\n"
                f"Wonhyuk William Chung"
            )
        else:
            # 0.0점: 실제 사유(지각 마감 초과 vs 본문 누락) 반영
            if "late cutoff" in item["reason_en"].lower():
                return (
                    f"Dear {name},\n\n"
                    f"Your assignment submission was received after the late submission deadline (Score: 0.0).\n"
                    f"- Task: {task_id}\n"
                    f"- Score: {score:.1f} / 1.0\n"
                    f"- Reason: {item['reason_en']}\n\n"
                    f"Best regards,\n"
                    f"Wonhyuk William Chung"
                )
            else:
                return (
                    f"Dear {name},\n\n"
                    f"We could not verify the content of your assignment in the email body (Score: 0.0).\n"
                    f"- Task: {task_id}\n"
                    f"- Score: {score:.1f} / 1.0\n"
                    f"- Reason: {item['reason_en']}\n\n"
                    f"Please re-submit your assignment with the actual content/links included in the body text.\n\n"
                    f"Best regards,\n"
                    f"Wonhyuk William Chung"
                )


def ensure_chrome_running(log: logging.Logger) -> bool:
    """전용 Chrome 실행 확인 및 자동 기동."""
    start_script = BASE_DIR / "bin" / "start_grader_chrome.sh"
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{CDP_PORT}/json/version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            log.info("✅ 전용 Chrome이 이미 실행 중입니다")
            return True
    except Exception:
        pass

    log.info("🚀 전용 Chrome 기동 중...")
    result = subprocess.run(
        [str(start_script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        log.error(f"❌ Chrome 기동 실패: {result.stderr}")
        return False
    log.info(result.stdout.strip())
    return True


def dismiss_popups(page, log: logging.Logger | None = None):
    """Gmail 프로모션/알림 다이얼로그 자동 닫기."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        dialog_btns = page.locator(
            'div[role="dialog"] button:has-text("Not now"), '
            'div[role="dialog"] button:has-text("No thanks"), '
            'div[role="dialog"] button:has-text("Dismiss"), '
            'div[role="dialog"] button:has-text("다음에"), '
            'div[role="dialog"] button:has-text("닫기"), '
            'div[role="dialog"] [aria-label="Close"], '
            'div[role="dialog"] [aria-label="닫기"]'
        )
        if dialog_btns.count() > 0 and dialog_btns.first.is_visible():
            if log:
                log.info("  ⚠️ 다이얼로그 팝업 감지되어 닫기 실행")
            dialog_btns.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


def stop_chrome(log: logging.Logger):
    """전용 Chrome만 안전 종료."""
    stop_script = BASE_DIR / "bin" / "stop_grader_chrome.sh"
    try:
        result = subprocess.run(
            [str(stop_script)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        log.info(result.stdout.strip())
    except Exception as e:
        log.warning(f"⚠️ Chrome 종료 중 오류: {e}")


def _get_keepass_env(key: str) -> str:
    """KeePass hourly.env.local 항목에서 환경변수 값을 조회한다."""
    try:
        env = os.environ.copy()
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
        raw = subprocess.run(
            ["secret-tool", "lookup", "Title", "hourly.env.local"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        ).stdout
        for line in raw.splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def send_alert(
    title: str, body: str, tags: str = "mortar_board", priority: str = "default"
):
    """Telegram 봇으로 알림 전송 (KeePass hourly.env.local 항목 참조)."""
    bot_token = os.environ.get("HERMES_USER_BOT") or _get_keepass_env("HERMES_USER_BOT")
    channel = os.environ.get("TELEGRAM_HOME_CHANNEL_NAME") or _get_keepass_env(
        "TELEGRAM_HOME_CHANNEL_NAME"
    )
    if not bot_token or not channel:
        return  # 미설정 시 알림 생략
    # @prefix 보장
    if not channel.startswith("@") and not channel.lstrip("-").isdigit():
        channel = f"@{channel}"
    emoji = "🚨" if priority == "high" else "📢"
    message = f"{emoji} <b>{title}</b>\n{body}"
    try:
        subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                "-d",
                f"chat_id={channel}",
                "-d",
                "parse_mode=HTML",
                "-d",
                f"text={message}",
            ],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


# 하위 호환용 별칭
send_ntfy = send_alert


def run_grading(
    task_id: str,
    grace_track: str | None = None,
    student_filter: str | None = None,
    dry_run: bool = False,
    log: logging.Logger | None = None,
):
    """메인 채점 + 시트 동기화 + 답장 발송 파이프라인."""
    if log is None:
        log = setup_logging(task_id)

    log.info(f"{'='*60}")
    log.info(f"🎯 자동 채점 시작: 과제 {task_id}")
    if grace_track:
        log.info(f"   → Grace-period 마감 모드: 트랙 {grace_track}")
    if student_filter:
        log.info(f"   → 특정 학생 필터: {student_filter}")
    if dry_run:
        log.info(f"   → DRY-RUN 모드 (시트/답장 없음)")
    log.info(f"   → 시각: {datetime.now(KST).isoformat()}")
    log.info(f"{'='*60}")

    # Step 1: 수강생 명단 로드
    log.info("🚀 [Step 1] 수강생 명단(SSOT) 로드 중...")
    students_by_id, name_to_id, email_to_id = parse_students()
    log.info(f"✅ 총 {len(students_by_id)}명 수강생 로드 완료.")

    # 3자리 입력 시 앞 7자리 '2026300' 자동채움 (예: 883 -> 2026300883)
    target_student_id = None
    if student_filter:
        s_filter = student_filter.strip()
        if re.match(r"^\d{3}$", s_filter):
            target_student_id = f"2026300{s_filter}"
        elif s_filter in students_by_id:
            target_student_id = s_filter
        else:
            for sid in students_by_id:
                if sid.endswith(s_filter):
                    target_student_id = sid
                    break
            if not target_student_id:
                target_student_id = s_filter

        if target_student_id in students_by_id:
            s_name = students_by_id[target_student_id]["eng_name"]
            log.info(
                f"   🎯 학생 학번 자동완성: '{student_filter}' → '{target_student_id}' ({s_name})"
            )
        else:
            log.info(f"   🎯 학생 학번: '{target_student_id}'")

    # Step 2: Chrome CDP 연결
    if not ensure_chrome_running(log):
        log.error("❌ Chrome 기동 실패. 종료합니다.")
        send_alert(
            "❌ 채점 실패",
            f"과제 {task_id}: Chrome 기동 실패",
            tags="rotating_light",
            priority="high",
        )
        return

    stats = {"graded": 0, "replied": 0, "failed": 0, "skipped": 0}

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Gmail 이동 및 로그인 여부 확인
            if "mail.google.com" not in page.url:
                page.goto("https://mail.google.com/")
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            if "accounts.google.com" in page.url:
                log.error("❌ Gmail 로그인 페이지로 리다이렉트됨 — 로그인 필요")
                send_alert(
                    "❌ 채점 실패",
                    f"과제 {task_id}: Gmail 로그인 필요",
                    tags="rotating_light",
                    priority="high",
                )
                return
            log.info(f"✅ Gmail 로드됨: {page.url}")

            # 검색 쿼리 구성
            task_num = task_id  # "0.4"
            wk_num = int(task_id.split(".")[1])
            wk_start = SEMESTER_START + timedelta(weeks=wk_num - 1)
            search_after = wk_start.strftime("%Y/%m/%d")
            if target_student_id:
                search_query = (
                    f'("{task_num}" OR "과제 {task_num}" OR "assignment {task_num}") '
                    f"{target_student_id} after:{search_after} -from:comments-noreply@docs.google.com"
                )
            else:
                search_query = (
                    f'("{task_num}" OR "과제 {task_num}" OR "assignment {task_num}") '
                    f"after:{search_after} -from:comments-noreply@docs.google.com"
                )
            log.info(f"🔍 Gmail 검색: {search_query}")

            # 검색창 UI 대신 Gmail 검색 URL로 직접 이동
            import urllib.parse

            encoded = urllib.parse.quote(search_query)
            page.goto(f"https://mail.google.com/mail/u/0/#search/{encoded}")
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)

            dismiss_popups(page, log)
            email_rows = page.locator("table.F.cf.zt:visible tr.zA:visible")
            row_count = email_rows.count()
            log.info(f"📬 총 {row_count}개 메일 스레드 검색됨")

            if row_count == 0:
                fallback_query = (
                    f"{task_num} after:{search_after} "
                    f"-from:comments-noreply@docs.google.com"
                )
                encoded_fb = urllib.parse.quote(fallback_query)
                page.goto(f"https://mail.google.com/mail/u/0/#search/{encoded_fb}")
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                page.wait_for_timeout(5000)
                dismiss_popups(page, log)
                email_rows = page.locator("table.F.cf.zt:visible tr.zA:visible")
                row_count = email_rows.count()
                log.info(f"📬 재검색 결과: {row_count}개 스레드")

            collected = []
            page_num = 1

            while True:
                dismiss_popups(page, log)
                email_rows = page.locator("table.F.cf.zt:visible tr.zA:visible")
                row_count = email_rows.count()
                log.info(
                    f"\n📑 [페이지 {page_num}] {row_count}개 메일 스레드 순회 시작"
                )

                for idx in range(row_count):
                    log.info(
                        f"\n--- [페이지 {page_num} 스레드 {idx + 1}/{row_count}] ---"
                    )
                    try:
                        dismiss_popups(page)
                        rows_current = page.locator(
                            "table.F.cf.zt:visible tr.zA:visible"
                        )
                        if idx >= rows_current.count():
                            break
                        target_row = rows_current.nth(idx)

                        sub_el = target_row.locator("span.bog")
                        subject = (
                            sub_el.inner_text().strip() if sub_el.count() > 0 else ""
                        )

                        sender_el = target_row.locator("div.yW span[name]")
                        sender_name = (
                            (
                                sender_el.first.get_attribute("name")
                                or sender_el.first.inner_text()
                            )
                            if sender_el.count() > 0
                            else ""
                        )

                        date_el = target_row.locator("td.xW span")
                        date_str = (
                            date_el.first.get_attribute("title")
                            if date_el.count() > 0
                            else ""
                        )
                        if not date_str and date_el.count() > 0:
                            date_str = date_el.first.inner_text()

                        # ── student_filter 고속 스킵 ────────────────────────
                        if target_student_id:
                            fast_match = (
                                (target_student_id in subject)
                                or (student_filter and student_filter in subject)
                                or (student_filter and student_filter in sender_name)
                            )
                            # 10자리 학번 추출 후 일치 검사
                            m_id = re.search(r"2026\d{6}", subject)
                            if m_id:
                                sid_found = m_id.group(0)
                                if sid_found == target_student_id or (
                                    student_filter
                                    and sid_found.endswith(student_filter)
                                ):
                                    fast_match = True

                            if not fast_match:
                                log.info(
                                    f"   메시지 제목: '{subject}', 발신자: '{sender_name}'"
                                    f"\n   ⏭️ [고속 스킵] 학생 필터 '{target_student_id}' 불일치"
                                )
                                stats["skipped"] += 1
                                continue
                        # ───────────────────────────────────────────────────

                        # ── Grace-period 고속 스킵 ──────────────────────────
                        # 목록 뷰에서 학번 추출 → 트랙 판별 → 대상 아니면 클릭 없이 스킵
                        if grace_track:
                            fast_sid = None
                            m_id = re.search(r"2026\d{6}", subject)
                            if m_id:
                                fast_sid = m_id.group(0)
                            if fast_sid and fast_sid in students_by_id:
                                fast_track = students_by_id[fast_sid]["track"]
                                if fast_track != grace_track:
                                    log.info(
                                        f"   메시지 제목: '{subject}', 발신자: '{sender_name}'"
                                        f"\n   ⏭️ [고속 스킵] 트랙 {fast_track} → 대상 아님 (대상: {grace_track})"
                                    )
                                    stats["skipped"] += 1
                                    continue
                        # ───────────────────────────────────────────────────

                        try:
                            target_row.click(timeout=10000)
                        except Exception:
                            dismiss_popups(page, log)
                            target_row.click(timeout=10000, force=True)

                        page.wait_for_timeout(2500)
                        thread_url = page.url

                        messages = page.locator("div.adn.ads")
                        msg_count = messages.count()
                        log.info(
                            f"   메시지 수: {msg_count}, 제목: '{subject}', 발신자: '{sender_name}'"
                        )

                        is_replied = False
                        student_msgs = []

                        for m_idx in range(msg_count):
                            m = messages.nth(m_idx)
                            s_email_el = m.locator("span.gD")
                            s_email = (
                                s_email_el.get_attribute("email")
                                if s_email_el.count() > 0
                                else ""
                            )
                            if "wonhyukc@stu.ac.kr" in s_email.lower():
                                is_replied = True
                            else:
                                body_el = m.locator("div.a3s.aiL")
                                body_text = (
                                    body_el.inner_text() if body_el.count() > 0 else ""
                                )
                                d_el = m.locator("span.g3")
                                m_date_str = ""
                                if d_el.count() > 0:
                                    m_date_str = (
                                        d_el.first.get_attribute("title")
                                        or d_el.first.inner_text()
                                    )
                                student_msgs.append(
                                    {
                                        "sender_email": s_email,
                                        "body": body_text,
                                        "date_str": m_date_str,
                                    }
                                )

                        # 학생 원본 메시지 기준 추출 (교수 답장 시각 오염 방지)
                        if student_msgs:
                            student_submission_msg = student_msgs[0]
                            last_sender_email = student_submission_msg["sender_email"]
                            last_msg_body = student_submission_msg["body"]
                            last_msg_date_str = (
                                student_submission_msg["date_str"] or date_str
                            )
                        else:
                            last_sender_email = ""
                            last_msg_body = ""
                            last_msg_date_str = date_str

                        # 학번 추출
                        extracted_sid = None
                        m_id = re.search(r"2026\d{6}", subject)
                        if m_id:
                            extracted_sid = m_id.group(0)
                        if not extracted_sid and last_sender_email:
                            clean_email = last_sender_email.lower().strip()
                            if clean_email in email_to_id:
                                extracted_sid = email_to_id[clean_email]
                            else:
                                m_em = re.search(r"2026\d{6}", clean_email)
                                if m_em:
                                    extracted_sid = m_em.group(0)
                        if not extracted_sid and sender_name:
                            clean_name = re.sub(r"\s+", "", sender_name).lower()
                            if clean_name in name_to_id:
                                extracted_sid = name_to_id[clean_name]

                        student_info = (
                            students_by_id.get(extracted_sid) if extracted_sid else None
                        )

                        # 특정 학생 필터 모드
                        if student_filter:
                            match_sid = False
                            if student_info and (
                                student_filter in student_info["id"]
                                or student_info["id"].endswith(student_filter)
                            ):
                                match_sid = True
                            elif student_filter in subject:
                                match_sid = True

                            if not match_sid:
                                log.info(
                                    f"   ⏭️ [학생 필터] '{student_filter}' 불일치 → 스킵 (ID: {extracted_sid})"
                                )
                                stats["skipped"] += 1
                                back_btn = page.locator(
                                    'div[aria-label="Back to search"], div[aria-label="검색결과로 돌아가기"], div[act="19"]'
                                )
                                if back_btn.count() > 0 and back_btn.first.is_visible():
                                    back_btn.first.click()
                                else:
                                    page.go_back()
                                page.wait_for_timeout(2000)
                                continue

                        # Grace-period 모드: 해당 트랙만 처리
                        if (
                            grace_track
                            and student_info
                            and student_info["track"] != grace_track
                        ):
                            log.info(
                                f"   ⏭️ Grace-period 모드: 트랙 {student_info['track']} → 스킵 (대상: {grace_track})"
                            )
                            stats["skipped"] += 1
                            back_btn = page.locator(
                                'div[aria-label="Back to search"], div[aria-label="검색결과로 돌아가기"], div[act="19"]'
                            )
                            if back_btn.count() > 0 and back_btn.first.is_visible():
                                back_btn.first.click()
                            else:
                                page.go_back()
                            page.wait_for_timeout(2000)
                            continue

                        if not student_info:
                            log.warning(
                                f"   ⚠️ 수강생 매칭 실패 (Subject: {subject}, Sender: {sender_name})"
                            )
                        else:
                            log.info(
                                f"   👤 매칭: {student_info['eng_name']} ({student_info['id']}, 트랙{student_info['track']})"
                            )

                        # 날짜 파싱 (다중 포맷 지원 및 KST 보장)
                        email_dt = parse_gmail_date(last_msg_date_str, log=log)
                        formatted_date = datetime.now(KST).strftime("%-m/%-d")
                        if email_dt:
                            formatted_date = email_dt.strftime("%-m/%-d")
                            dt_str = email_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
                            log.info(
                                f"   📅 발송일시: {dt_str} (표시: {formatted_date}, 원본: '{last_msg_date_str}')"
                            )
                        else:
                            log.warning(
                                f"   ⚠️ 발송일시 파싱 실패 (원본: '{last_msg_date_str}') "
                                f"→ 금일 날짜({formatted_date})로 기록"
                            )

                        score, reason_en, reason_ko, details = evaluate_submission(
                            subject,
                            last_msg_body,
                            student_info,
                            email_dt,
                            task_id,
                            log=log,
                        )
                        log.info(f"   📊 채점: {score:.1f}점 | {reason_en} | {details}")
                        log.info(
                            f"   ✉️ 답장: {'완료(스킵)' if is_replied else '미답장(대상)'}"
                        )
                        stats["graded"] += 1

                        collected.append(
                            {
                                "student_info": student_info,
                                "extracted_sid": extracted_sid,
                                "sender_name": sender_name,
                                "sender_email": last_sender_email,
                                "subject": subject,
                                "score": score,
                                "reason_en": reason_en,
                                "reason_ko": reason_ko,
                                "date": formatted_date,
                                "is_replied": is_replied,
                                "last_msg_body": last_msg_body,
                                "thread_url": thread_url,
                            }
                        )

                        back_btn = page.locator(
                            'div[aria-label="Back to search"], div[aria-label="검색결과로 돌아가기"], div[act="19"]'
                        )
                        if back_btn.count() > 0 and back_btn.first.is_visible():
                            back_btn.first.click()
                        else:
                            page.go_back()
                        page.wait_for_timeout(2000)

                        # 단독 학생 필터 처리 시 1건 수집되면 즉시 순회 완료
                        if target_student_id and len(collected) > 0:
                            log.info(
                                f"🎯 타겟 학생({target_student_id}) 수집 완료 → 스레드 순회 종료"
                            )
                            break

                    except Exception as thread_err:
                        log.warning(
                            f"   ⚠️ 스레드 처리 중 오류 (스킵 후 계속): {thread_err}"
                        )
                        stats["failed"] += 1
                        try:
                            if "search" not in page.url:
                                back_btn = page.locator(
                                    'div[aria-label="Back to search"], div[aria-label="검색결과로 돌아가기"], div[act="19"]'
                                )
                                if back_btn.count() > 0 and back_btn.first.is_visible():
                                    back_btn.first.click()
                                else:
                                    page.go_back()
                                page.wait_for_timeout(2000)
                        except Exception:
                            pass

                # 단독 학생 필터 처리 시 수집 완료되면 다음 페이지도 불필요
                if target_student_id and len(collected) > 0:
                    break

                # 다음 페이지 버튼 확인
                dismiss_popups(page, log)
                next_btn = page.locator(
                    'div[aria-label="Next results"], div[aria-label="Older"], div[aria-label="다음 결과"], div[aria-label="이전 결과"]'
                )
                can_go_next = False
                for b_idx in range(next_btn.count()):
                    btn = next_btn.nth(b_idx)
                    if (
                        btn.is_visible()
                        and btn.get_attribute("aria-disabled") != "true"
                    ):
                        can_go_next = True
                        log.info(
                            f"⏩ [페이지 {page_num} 완료] 다음 페이지로 이동합니다..."
                        )
                        btn.click()
                        page.wait_for_timeout(4000)
                        page_num += 1
                        break

                if not can_go_next:
                    log.info("🏁 마지막 페이지까지 수집 완료.")
                    break

            # Step 3: 중복 제거 (학생별 최고점 유지)
            log.info("\n🚀 [Step 3] 학생별 중복 제거...")
            deduped = {}
            for sub in collected:
                sid = sub["extracted_sid"]
                if not sid or not sub["student_info"]:
                    continue
                if sid not in deduped or sub["score"] > deduped[sid]["score"]:
                    deduped[sid] = sub

            final_list = list(deduped.values())
            log.info(f"✅ 유효 제출: {len(final_list)}명")

            # Step 4: 시트 동기화
            wk_num = task_id.split(".")[1]
            if not dry_run:
                log.info("\n🚀 [Step 4] 구글 시트 멱등 Upsert...")
                py_rows = []
                web_rows = []

                for item in final_list:
                    s_info = item["student_info"]
                    # 11열 구조: No, wk, ID, Track, Score, Type1, Type2, Reason, Date, Name, Subject
                    if s_info["track"] == "4":
                        row = [
                            0,
                            wk_num,
                            s_info["id"],
                            "4",
                            f"{item['score']:.2f}",
                            "hw",
                            task_id,
                            item["reason_ko"],
                            item["date"],
                            s_info["eng_name"],
                            item["subject"],
                        ]
                        py_rows.append(row)
                    else:
                        row = [
                            0,
                            wk_num,
                            s_info["id"],
                            s_info["track"],
                            f"{item['score']:.2f}",
                            "hw",
                            task_id,
                            item["reason_en"],
                            item["date"],
                            s_info["eng_name"],
                            item["subject"],
                        ]
                        web_rows.append(row)

                if py_rows:
                    log.info(f"📝 파이썬 4반: {len(py_rows)}건 Upsert")
                    upsert_grades_to_sheet(py_rows, course="py")
                if web_rows:
                    log.info(f"📝 웹 1/2반: {len(web_rows)}건 Upsert")
                    upsert_grades_to_sheet(web_rows, course="web")
            else:
                log.info("\n⏭️ [Step 4] DRY-RUN: 시트 동기화 생략")

            # Step 5: 미답장 자동 답장
            if not dry_run:
                log.info("\n🚀 [Step 5] 미답장 자동 답장 발송...")
                unreplied = [item for item in final_list if not item["is_replied"]]
                log.info(f"📬 미답장: {len(unreplied)}건")

                for idx, item in enumerate(unreplied):
                    s_info = item["student_info"]
                    log.info(
                        f"   → [{idx+1}/{len(unreplied)}] {s_info['eng_name']} ({s_info['id']})"
                    )
                    page.goto(item["thread_url"])
                    page.wait_for_timeout(3000)

                    reply_body = build_reply_body(item, task_id)
                    log.info(
                        f"      ✉️ 발송 답장 본문 미리보기 (점수: {item['score']}점, 사유: {item['reason_en']}):\n"
                        + "\n".join(
                            "         | " + line for line in reply_body.splitlines()
                        )
                    )

                    try:
                        reply_btn = page.locator(
                            'span[role="link"]:has-text("Reply"), span[role="link"]:has-text("답장"), '
                            'div[aria-label*="Reply"], div[aria-label*="답장"], '
                            'div[data-tooltip*="Reply"], div[data-tooltip*="답장"]'
                        )
                        if reply_btn.count() > 0 and reply_btn.first.is_visible():
                            reply_btn.first.click()
                        else:
                            page.keyboard.press("r")
                        page.wait_for_timeout(2000)

                        textbox = page.locator(
                            'div[role="textbox"][aria-label*="Message Body"], '
                            'div[role="textbox"][aria-label*="본문"], '
                            'div[role="textbox"]:visible'
                        )
                        if textbox.count() > 0:
                            textbox.first.fill(reply_body)
                            page.wait_for_timeout(1000)
                            page.keyboard.press("Control+Enter")
                            page.wait_for_timeout(3000)
                            log.info(f"      ✅ 답장 발송 성공!")
                            stats["replied"] += 1
                        else:
                            log.error(f"      ❌ 답장 입력창 없음")
                            stats["failed"] += 1
                    except Exception as e:
                        log.error(f"      ❌ 답장 오류: {e}")
                        stats["failed"] += 1
            else:
                log.info("\n⏭️ [Step 5] DRY-RUN: 답장 발송 생략")

            browser.close()

    except Exception as e:
        log.error(f"❌ 치명적 오류: {e}")
        stats["failed"] += 1

    # 결과 요약
    summary = (
        f"과제 {task_id} 자동 채점 완료\n"
        f"• 채점: {stats['graded']}건\n"
        f"• 답장: {stats['replied']}건\n"
        f"• 실패: {stats['failed']}건\n"
        f"• 스킵: {stats['skipped']}건"
    )
    log.info(f"\n{'='*60}")
    log.info(f"✨ {summary}")
    log.info(f"{'='*60}")

    if not dry_run:
        tags = "tada" if stats["failed"] == 0 else "warning"
        priority = "default" if stats["failed"] == 0 else "high"
        send_alert(
            f"📊 과제 {task_id} 채점 완료", summary, tags=tags, priority=priority
        )


def main():
    if len(sys.argv) == 1:
        current_task = calculate_current_task()
        print(f"""\
📋 이메일 과제 자동 채점 CLI (email-grade.sh)

💡 현재 주차 기준 기본 과제: {current_task}

사용법:
  ./bin/email-grade.sh <과제번호> [학번필터] [옵션]

기본 예시:
  ./bin/email-grade.sh 0.4                 # 과제 0.4 전체 학생 채점 + 시트 반영 + 미답장 답장
  ./bin/email-grade.sh 0.4 883             # 과제 0.4 중 특정 학생(학번 뒷3자리 883)만 단독 채점
  ./bin/email-grade.sh 4 2026300883        # 과제 0.4 중 10자리 학번 단독 채점 (4는 0.4로 자동 변환)
  ./bin/email-grade.sh 0.4 --dry-run       # 시트 반영 및 답장 없이 채점 결과만 미리보기
  ./bin/email-grade.sh 0.4 883 --dry-run   # 883 학생 단독 Dry-run 미리보기

분반별 Grace-period 모드:
  ./bin/email-grade.sh 0.4 --grace web1    # 1반(web1, 월 16:00 지각마감) 대상만 채점
  ./bin/email-grade.sh 0.4 --grace web2    # 2반(web2, 월 13:00 지각마감) 대상만 채점
  ./bin/email-grade.sh 0.4 --grace py      # 4반(파이썬, 월 09:00 지각마감) 대상만 채점

자세한 옵션 보기:
  ./bin/email-grade.sh --help
""")
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="이메일 과제 자동 채점 CLI. 위치 인자(0.4 883 등) 및 옵션 플래그 모두 지원."
    )
    # 위치 인자 (e.g. `0.4 883` 또는 `0.4`)
    parser.add_argument(
        "positional_args",
        nargs="*",
        help="위치 인자: [과제번호 (예: 0.4 또는 4)] [학번 (예: 883 또는 2026300883)]",
    )
    parser.add_argument(
        "--task", "-t", type=str, help="과제 번호 (예: 0.4, 4). 미지정 시 자동 계산"
    )
    parser.add_argument(
        "--student",
        "-s",
        type=str,
        help="특정 학생 학번 필터 (예: 883 또는 2026300883)",
    )
    parser.add_argument(
        "--grace",
        type=str,
        choices=["py", "web1", "web2"],
        help="Grace-period 마감 모드 (해당 트랙만 처리)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="시트/답장 없이 채점만 미리보기"
    )
    args = parser.parse_args()

    # 위치 인자 해석 (e.g. `python3 bin/auto_grade_email.py 0.4 883`)
    task_arg = args.task
    student_arg = args.student

    if args.positional_args:
        pos0 = args.positional_args[0]
        # 첫 번째 인자가 0.x 또는 숫자 형태인 경우 task_id로 처리
        if re.match(r"^(?:0\.)?\d+$", pos0):
            if not task_arg:
                task_arg = pos0 if pos0.startswith("0.") else f"0.{pos0}"
        elif not student_arg:
            student_arg = pos0

        if len(args.positional_args) > 1 and not student_arg:
            student_arg = args.positional_args[1]

    # task_id 정규화 (4 -> 0.4)
    if task_arg:
        task_id = task_arg if task_arg.startswith("0.") else f"0.{task_arg}"
    else:
        task_id = calculate_current_task()

    grace_track = None
    if args.grace:
        grace_map = {"py": "4", "web1": "1", "web2": "2"}
        grace_track = grace_map[args.grace]

    log = setup_logging(task_id)
    log.info(
        f"🎓 auto_grade_email.py 시작 (task={task_id}, student={student_arg}, grace={args.grace}, dry_run={args.dry_run})"
    )

    run_grading(
        task_id,
        grace_track=grace_track,
        student_filter=student_arg,
        dry_run=args.dry_run,
        log=log,
    )


if __name__ == "__main__":
    main()
