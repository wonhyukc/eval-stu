import os
import json
import re
from typing import Any

Credentials: Any
build: Any
google: Any

try:
    from google.oauth2.service_account import Credentials  # type: ignore[no-redef]
    from googleapiclient.discovery import build  # type: ignore[no-redef]
    import google.auth  # type: ignore[no-redef]
except ImportError:
    Credentials = None  # type: ignore[no-redef]
    build = None  # type: ignore[no-redef]
    google = None  # type: ignore[no-redef]

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def load_course_config(base_dir, course="py"):
    settings_file = os.path.join(base_dir, "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return settings.get("courses", {}).get(course)
    return None


def get_sheet_service(base_dir):
    # 크레덴셜 후보 경로 순서대로 탐색
    candidates = [
        os.path.join(base_dir, "secret.json"),
        os.path.expanduser("~/nvme_data/prj/exchange/service-account.json"),
    ]
    secret_path = next((p for p in candidates if os.path.exists(p)), None)

    if secret_path:
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    else:
        try:
            import subprocess

            res = subprocess.run(
                ["secret-tool", "lookup", "Title", "drive-api"],
                capture_output=True,
                text=True,
            )
            if res.stdout.strip():
                data = json.loads(res.stdout.strip())
                creds = Credentials.from_service_account_info(data, scopes=SCOPES)
            else:
                print(
                    "ℹ️ 서비스 계정 키 파일이 없으므로 Application Default Credentials를 시도합니다."
                )
                creds, _ = google.auth.default(scopes=SCOPES)
        except Exception:
            print(
                "ℹ️ 서비스 계정 키 파일이 없으므로 Application Default Credentials를 시도합니다."
            )
            creds, _ = google.auth.default(scopes=SCOPES)

    # cache_discovery=False 로 무한 지연 에러 원천 차단
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_target_sheet_title(service, spreadsheet_id, target_gid):
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = sheet_metadata.get("sheets", "")
    for s in sheets:
        props = s.get("properties", {})
        if props.get("sheetId") == target_gid:
            return props.get("title")
    return None


def get_max_no(service, spreadsheet_id, sheet_title):
    range_name = f"{sheet_title}!A:A"
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        max_no = 0
        for row in values:
            if row:
                clean_no = str(row[0]).replace("'", "").strip()
                if clean_no.isdigit():
                    max_no = max(max_no, int(clean_no))
        return max_no
    except Exception as e:
        print(f"⚠️ 일련번호(no) 조회 실패. 기본값 0 사용: {e}")
        return 0


def normalize_row_to_11cols(row):
    """구버전 호환용 11열 변환 함수."""
    return normalize_row_to_13cols(row)[:11]


def normalize_row_to_13cols(row, row_num: int = 2, course: str = "web1"):
    """
    행 데이터를 신규 표준 13열 구조로 정규화합니다.
    [No, wk, ID, Track, ScaledScore, Score, Type1, Type2, Reason, Date, Name, Subject, Appeal] (A~M)
    - E열: Scaled Score 수식 (M열에서 이동)
    - F열: 루브릭 원점수 (Score)
    - G열: Type1
    - H열: Type2
    - I열: Reason
    - J열: Date
    - K열: Name (VLOOKUP 수식 보존)
    - L열: Subject
    - M열: Appeal Response
    """
    r = list(row)
    scaled_formula = make_scaled_score_formula(row_num)
    name_formula = make_name_vlookup_formula(row_num, course)

    # 1. 이미 13열 구조인 경우
    if len(r) >= 13:
        # E열이 비어있거나 수식이 아니면 수식 주입
        if not str(r[4]).startswith("="):
            r[4] = scaled_formula
        # K열이 비어있거나 수식이 아니면 VLOOKUP 수식 주입
        if not str(r[10]).startswith("="):
            r[10] = name_formula
        return r[:13]

    # 2. 기존 11열 구조인 경우 (끝의 빈 셀이 생략된 행 포함)
    # [No, wk, ID, Track, Score, Type1, Type2, Reason, Date, Name, Subject]
    if 6 <= len(r) <= 11 and str(r[5]).strip().lower() in [
        "hw",
        "class",
        "mid",
        "fin",
        "peer",
        "lab",
    ]:
        r.extend([""] * (11 - len(r)))
        no, wk, sid, track, score, t1, t2, reason, dt, _, subj = r
        return [
            no,
            wk,
            sid,
            track,
            scaled_formula,
            score,
            t1,
            t2,
            reason,
            dt,
            name_formula,
            subj,
            "",
        ]

    # 3. 구 9열 구조인 경우: [no, sid, track, score, ctype, reason, dt, name, subj]
    if len(r) == 9 and not (str(r[1]).isdigit() and int(r[1]) < 16):
        no, sid, track, score, ctype, reason, dt, _, subj = r
        clean_t = str(ctype).replace("과제", "").replace("'", "").strip()
        m = re.search(r"0\.(\d+)", clean_t)
        wk = m.group(1) if m else ""
        return [
            no,
            wk,
            sid,
            track,
            scaled_formula,
            score,
            "hw",
            ctype,
            reason,
            dt,
            name_formula,
            subj,
            "",
        ]

    # 4. 기타 불완전한 행: 13열로 확장
    while len(r) < 13:
        r.append("")
    if not str(r[4]).startswith("="):
        r[4] = scaled_formula
    if not str(r[10]).startswith("="):
        r[10] = name_formula
    return r[:13]


def make_scaled_score_formula(row_num: int) -> str:
    """주어진 행 번호에 대한 E열(Scaled Score) 수식을 생성합니다.
    H열이 'lab'이면 주차별 실습 만점(3주차 9점, 그 외 10점) 대비 3.0점 스케일 환산,
    그 외는 F열(원점수) 그대로 반영.
    """
    return (
        f'=IF(H{row_num}="lab", '
        f"IF(B{row_num}=3, ROUND((F{row_num}/9)*3, 2), ROUND((F{row_num}/10)*3, 2)), "
        f"F{row_num})"
    )


def make_name_vlookup_formula(row_num: int, course: str = "web1") -> str:
    """주어진 행 번호에 대한 K열(Name) VLOOKUP 수식을 생성합니다.
    C열(학번)을 참조하여 progress 탭에서 학생명을 조회합니다.
    - web1, web2: progress C열(영문 성명)
    - py: progress B열(한글 성명)
    """
    clean_course = str(course).lower()
    if clean_course == "py":
        return f'=IFERROR(VLOOKUP(C{row_num}, progress!$A$5:$B, 2, FALSE), "")'
    return f'=IFERROR(VLOOKUP(C{row_num}, progress!$A$5:$C, 3, FALSE), "")'


TRACK_NORMALIZATION_MAP = {
    # 1반
    "1": "1",
    "01": "1",
    "web1": "1",
    "웹1": "1",
    "ice0001-01": "1",
    "761": "1",
    "15143": "1",
    # 2반
    "2": "2",
    "02": "2",
    "web2": "2",
    "웹2": "2",
    "ice0001-02": "2",
    "762": "2",
    "15144": "2",
    # 4반
    "4": "4",
    "04": "4",
    "python": "4",
    "파이썬": "4",
    "gpu0940-04": "4",
    "468": "4",
    "14712": "4",
}


def normalize_track(track_raw: Any) -> str:
    """트랙 표기를 대표 번호 ('1', '2', '4') 중 하나로 정규화."""
    if not track_raw:
        return ""
    clean = str(track_raw).replace("'", "").strip().lower()
    if clean in TRACK_NORMALIZATION_MAP:
        return TRACK_NORMALIZATION_MAP[clean]
    if clean.startswith("4"):
        return "4"
    if clean.startswith("1"):
        return "1"
    if clean.startswith("2"):
        return "2"
    return clean


def format_date_to_mmdd_hhmm(date_val: Any) -> str:
    """날짜 문자열을 'mm/dd hh:mm' (예: '09/30 20:15') 형식으로 변환."""
    if not date_val:
        return ""

    s = str(date_val).strip()
    if not s:
        return ""

    # 1. 이미 mm/dd hh:mm 형식인 경우 (예: '09/30 20:15' 또는 '9/30 20:15')
    m_direct = re.match(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})$", s)
    if m_direct:
        m, d, h, mn = m_direct.groups()
        return f"{int(m):02d}/{int(d):02d} {int(h):02d}:{mn}"

    clean_s = s.replace("\u202f", " ").replace("\xa0", " ").strip()

    # 2. Gmail 영문 날짜 형태: 'Wed, Sep 30, 2026, 8:15 PM' or 'Sep 30, 2026, 8:15 PM'
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    m_gmail = re.search(
        r"([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4}),?\s+(\d{1,2}):(\d{2})\s*(AM|PM)?",
        clean_s,
        re.IGNORECASE,
    )
    if m_gmail:
        mon_str, day_str, _, hr_str, min_str, ampm = m_gmail.groups()
        mon = months.get(mon_str.lower()[:3])
        if mon:
            hr = int(hr_str)
            if ampm:
                if ampm.upper() == "PM" and hr < 12:
                    hr += 12
                elif ampm.upper() == "AM" and hr == 12:
                    hr = 0
            return f"{mon:02d}/{int(day_str):02d} {hr:02d}:{min_str}"

    # 3. email.utils 표준 파싱 (예: 'Thu, 1 Oct 2026 12:10:00 +0900')
    import email.utils
    from datetime import timezone, timedelta

    kst = timezone(timedelta(hours=9))
    try:
        dt = email.utils.parsedate_to_datetime(clean_s)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=kst)
            else:
                dt = dt.astimezone(kst)
            return dt.strftime("%m/%d %H:%M")
    except Exception:
        pass

    # 4. 한국어 형태: '2026. 10. 1. 오후 8:15'
    m_ko = re.search(
        r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*(오전|오후)?\s*(\d{1,2}):(\d{2})",
        clean_s,
    )
    if m_ko:
        _, mon_k, day_k, ampm_k, hr_k, mn_k = m_ko.groups()
        h_k = int(hr_k)
        if ampm_k == "오후" and h_k < 12:
            h_k += 12
        elif ampm_k == "오전" and h_k == 12:
            h_k = 0
        return f"{int(mon_k):02d}/{int(day_k):02d} {h_k:02d}:{mn_k}"

    # 5. ISO 형태: '2026-10-01 18:06:00'
    m_iso = re.search(
        r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T\s]+(\d{1,2}):(\d{2}))?",
        clean_s,
    )
    if m_iso:
        _, mon_i, day_i, hr_i, mn_i = m_iso.groups()
        if hr_i and mn_i:
            return f"{int(mon_i):02d}/{int(day_i):02d} {int(hr_i):02d}:{mn_i}"
        return f"{int(mon_i):02d}/{int(day_i):02d}"

    # 6. 월/일만 있는 경우: '9/25'
    m_md = re.match(r"^(\d{1,2})/(\d{1,2})$", clean_s)
    if m_md:
        return f"{int(m_md.group(1)):02d}/{int(m_md.group(2)):02d}"

    return s


def apply_score_sheet_formatting(service, spreadsheet_id: str, sheet_id: int) -> None:
    """Scaled Score(E열), Score(F열) 우측 정렬 및 0.00 서식, Date(J열) 왼쪽 정렬 서식 적용."""
    requests = [
        # E열 (Scaled Score, col index 4) 우측 정렬 및 숫자 서식 (0.00)
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "RIGHT",
                        "numberFormat": {"type": "NUMBER", "pattern": "0.00"},
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.numberFormat",
            }
        },
        # F열 (Score 원점수, col index 5) 우측 정렬 및 숫자 서식 (0.00)
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": 5,
                    "endColumnIndex": 6,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "RIGHT",
                        "numberFormat": {"type": "NUMBER", "pattern": "0.00"},
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.numberFormat",
            }
        },
        # J열 (Date, col index 9) 왼쪽 정렬
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": 9,
                    "endColumnIndex": 10,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "LEFT",
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
    ]
    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
    except Exception as e:
        print(f"ℹ️ 시트 서식 적용 건너뜀 (권한 또는 API 제한): {e}")


def route_web_rows(rows_data):
    """web 강좌의 행 데이터에서 Track 컬럼을 분석하여

    1반(web1)과 2반(web2)으로 자동 분류합니다.
    11열 구조: Track은 인덱스 3 (D열)
    구 9열 구조: Track은 인덱스 2 (C열)
    """
    web1_rows = []
    web2_rows = []

    for row in rows_data:
        track_idx = 3 if len(row) > 9 else 2
        track_raw = str(row[track_idx]).strip() if len(row) > track_idx else ""
        norm = normalize_track(track_raw)
        if norm == "1":
            web1_rows.append(row)
        else:
            web2_rows.append(row)

    return web1_rows, web2_rows


# ── 2점 스케일 → 1.0점 스케일 점수 환산 (SSOT: 1docs/score-email.md) ──
SCORE_2_TO_1_MAP = {
    2.0: 1.0,  # 정상 만점
    1.8: 0.9,  # 관용 인정 (경미 오차)
    1.5: 0.5,  # 지각 제출 (양식 정상)
    1.3: 0.7,  # 형식 미흡
    1.0: 0.5,  # 특수 감점 (첨부 등) — 문맥에 따라 0.5 기본
    0.5: 0.2,  # 지각 + 형식 미흡
    0.0: 0.0,  # 미제출/불인정
}

# 2점 스케일 사유 → SSOT 1.0점 표준 사유 정규화 매핑
REASON_2SCALE_TO_SSOT = {
    # 한글 (K트랙)
    "정확한 양식/조건충족(+2)": "정상 제출 (기한내/정확한 양식)",
    # 영문 (E트랙)
    "Met all conditions (+2)": "On-time & Exact Format",
}


def is_lab_assignment(t1: Any, t2: Any) -> bool:
    """Type1 또는 Type2를 검사하여 실습(Lab) 과제 여부를 판정합니다.

    작은따옴표('), 접두어, 대소문자에 영향받지 않고 안전하게 판별합니다.
    예: Type1="hw", Type2="lab" 또는 "L3", "'lab", "'L3", "실습" 등
    """
    clean_t1 = str(t1 or "").replace("'", "").strip().lower()
    clean_t2 = str(t2 or "").replace("과제", "").replace("'", "").strip().lower()
    return (
        clean_t1 in ("lab", "실습")
        or clean_t2 in ("lab", "실습")
        or clean_t2.startswith("l")
    )


def convert_score_to_1scale(score_str: str) -> str:
    """2점 만점 스케일 점수를 1.0점 만점으로 환산.

    이미 1.0 스케일인 점수(0.0-1.0 범위)는 그대로 반환.
    """
    try:
        score = float(str(score_str).strip())
    except (ValueError, TypeError):
        return str(score_str)

    # 이미 1.0 스케일인지 판별: 1.0 이하이면 그대로
    if score <= 1.0:
        return str(score)

    # 2점 스케일 매핑
    if score in SCORE_2_TO_1_MAP:
        converted = SCORE_2_TO_1_MAP[score]
        return str(converted)

    # 매핑에 없는 경우 비례 환산 (score / 2)
    converted = round(score / 2.0, 2)
    return str(converted)


def convert_lab_score_to_3scale(raw_score: Any, max_score: float | int = 10.0) -> str:
    """실습(Lab) 과제 점수를 3.0점 만점 스케일로 환산.

    루브릭 원점수(총점 9점, 10점, 11점, 13점 등)를 SSOT 기준인 3.0점 만점으로 정규화합니다.
    계산식: round((raw_score / max_score) * 3.0, 2)
    만약 이미 3.0 이하 스케일로 입력된 경우(score <= 3.0 and max_score <= 3.0) 그대로 반환.
    '획득/만점'(예: '9/10') 형식의 문자열도 지원.
    """
    if raw_score is None:
        return "0.0"

    score_text = str(raw_score).strip()

    # "9/10" 형태의 분수형 문자열 파싱 지원
    if "/" in score_text:
        parts = score_text.split("/")
        try:
            val = float(parts[0].strip())
            denom = float(parts[1].strip())
            if denom > 0:
                converted = round(min(max(val / denom, 0.0), 1.0) * 3.0, 2)
                return str(converted)
        except (ValueError, IndexError):
            pass

    try:
        score = float(score_text)
    except (ValueError, TypeError):
        return score_text

    try:
        denom = float(max_score)
        if denom <= 0:
            denom = 10.0
    except (ValueError, TypeError):
        denom = 10.0

    # 이미 3.0 스케일(3.0점 만점) 이하로 기록된 경우 (denom <= 3.0)
    if denom <= 3.0 and score <= 3.0:
        return str(round(score, 2))

    # denom 기준으로 3.0점 비례 환산
    ratio = min(max(score / denom, 0.0), 1.0)
    converted = round(ratio * 3.0, 2)
    return str(converted)


def normalize_reason_to_ssot(reason: str) -> str:
    """2점 스케일 사유를 SSOT 표준 사유로 정규화.

    괄호 안에 점수(예: (1.8), (+2))가 포함된 사유를 표준 문구로 변환.
    """
    if not reason:
        return ""
    raw = str(reason).strip()

    # 직접 매핑
    if raw in REASON_2SCALE_TO_SSOT:
        return REASON_2SCALE_TO_SSOT[raw]

    # 괄호+점수 패턴 제거: "조건위반(제목양식오류) (1.8)" → "조건위반(제목양식오류)"
    cleaned = re.sub(r"\s*\(\+?\d+\.?\d*\)\s*$", "", raw).strip()
    if cleaned in REASON_2SCALE_TO_SSOT:
        return REASON_2SCALE_TO_SSOT[cleaned]

    # "지각 제출 (정확한 양식/조건충족(+2))" → "지각 제출 (다음 수업 시작 전)"
    if "지각 제출" in raw or "Late submission" in raw:
        inner_match = re.search(r"\((.+)\)", raw)
        if inner_match:
            inner = inner_match.group(1)
            if "조건충족" in inner or "all conditions" in inner.lower():
                if "지각" in raw:
                    return "지각 제출 (다음 수업 시작 전)"
                return "Late submission (Before next class)"
        if "지각" in raw:
            return "지각 제출 (다음 수업 시작 전)"
        return "Late submission (Before next class)"

    # "조건위반(제목양식오류)" → "경미한 양식 오차 (괄호/불필요 기호)" 또는 유사 매핑
    if "조건위반" in raw:
        if "제목양식오류" in raw:
            return "경미한 양식 오차 (괄호/불필요 기호)"
        if "첨부있음" in raw:
            return "경미한 양식 오차 (괄호/불필요 기호)"
        return raw  # 알 수 없는 조건위반은 원문 유지

    if "Violation" in raw:
        if "Title format error" in raw:
            return "Minor format issue (Brackets/Extra text)"
        if "Attachment included" in raw:
            return "Minor format issue (Brackets/Extra text)"
        return raw

    return raw


REASON_KO_TO_EN_MAP = {
    "정확한 양식/조건충족(+2)": "On-time & Exact Format",
    "정상 제출 (기한내/정확한 양식)": "On-time & Exact Format",
    "정상 제출": "On-time & Exact Format",
    "경미한 양식 오차 (괄호/불필요 기호)": "Minor format issue (Brackets/Extra text)",
    "제목 학번 또는 과제명 누락": "Missing Student ID or 0.x in Subject",
    "제목양식오류": "Title format error",
    "지각 제출 (다음 수업 시작 전)": "Late submission (Before next class)",
    "지각 제출": "Late submission",
    "지각 + 제목 학번 누락": "Late & Format Issue (Missing ID)",
    "미제출": "No submission",
    "본문 미작성(단순 회신)": "Empty Body / Quoted Text Only",
    "본문 미작성": "Empty Body / Quoted Text Only",
    "학번 식별 불가": "Cannot identify student ID",
    "수동 확인 요망(양식불일치/타주차)": "Manual review required (Format mismatch)",
    "수동 확인 요망": "Manual review required",
    "첨부없음": "No attachment",
    "첨부있음": "Attachment included",
}


def translate_reason_to_en(reason: str) -> str:
    """웹(E트랙) 시트 언어 정책을 준수하기 위해 한글 사유를 영문으로 변환."""
    if not reason:
        return ""

    raw = str(reason).strip()
    if raw in REASON_KO_TO_EN_MAP:
        return REASON_KO_TO_EN_MAP[raw]

    # "지각 제출 (...)" 패턴 처리
    prefix_len = len("지각 제출")
    if raw.startswith("지각 제출"):
        inner = raw[prefix_len:].strip()
        if inner.startswith("(") and inner.endswith(")"):
            inner_en = translate_reason_to_en(inner[1:-1])
            return f"Late submission ({inner_en})"
        return "Late submission"

    # "조건위반(...)" 패턴 처리
    if "조건위반" in raw:
        raw = raw.replace("조건위반", "Violation")
        raw = raw.replace("첨부없음", "No attachment")
        raw = raw.replace("첨부있음", "Attachment included")
        raw = raw.replace("제목양식오류", "Title format error")
        raw = raw.replace("제목오류(0.12)", "Subject error (0.12)")
        return raw

    for ko, en in REASON_KO_TO_EN_MAP.items():
        raw = raw.replace(ko, en)

    return raw


REASON_EN_TO_KO_MAP = {
    "On-time & Exact Format": "정상 제출 (기한내/정확한 양식)",
    "Minor format issue (Brackets/Extra text)": "경미한 양식 오차 (괄호/불필요 기호)",
    "Missing Student ID or 0.x in Subject": "제목 학번 또는 과제명 누락",
    "Title format error": "제목양식오류",
    "Late submission (Before next class)": "지각 제출 (다음 수업 시작 전)",
    "Late submission": "지각 제출",
    "Late & Format Issue (Missing ID)": "지각 + 제목 학번 누락",
    "No submission": "미제출",
    "Empty Body / Quoted Text Only": "본문 미작성(단순 회신)",
    "Cannot identify student ID": "학번 식별 불가",
    "Manual review required (Format mismatch)": "수동 확인 요망(양식불일치/타주차)",
    "Manual review required": "수동 확인 요망",
    "No attachment": "첨부없음",
    "Attachment included": "첨부있음",
    "Subject error (0.12)": "제목오류(0.12)",
    "Subject error(0.12)": "제목오류(0.12)",
}


def translate_reason_to_ko(reason: str) -> str:
    """파이썬(K트랙) 시트 언어 정책을 준수하기 위해 영문 사유를 한글로 변환."""
    if not reason:
        return ""

    raw = str(reason).strip()
    if raw in REASON_EN_TO_KO_MAP:
        return REASON_EN_TO_KO_MAP[raw]

    # "Late submission (...)" 패턴 처리
    prefix_len = len("Late submission")
    if raw.startswith("Late submission"):
        inner = raw[prefix_len:].strip()
        if inner.startswith("(") and inner.endswith(")"):
            inner_ko = translate_reason_to_ko(inner[1:-1])
            return f"지각 제출 ({inner_ko})"
        return "지각 제출"

    # "Violation(...)" 패턴 처리
    if "Violation" in raw:
        raw = raw.replace("Violation", "조건위반")
        raw = raw.replace("No attachment", "첨부없음")
        raw = raw.replace("Attachment included", "첨부있음")
        raw = raw.replace("Title format error", "제목양식오류")
        raw = raw.replace("Subject error (0.12)", "제목오류(0.12)")
        raw = raw.replace("Subject error(0.12)", "제목오류(0.12)")
        return raw

    for en, ko in REASON_EN_TO_KO_MAP.items():
        raw = raw.replace(en, ko)

    return raw


def _translate_formula_rows(formula: str, row_offset: int) -> str:
    """행 이동에 맞춰 상대 행 참조만 옮기고 절대 참조·문자열·시트명은 보존합니다."""
    tokens = re.compile(
        r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'|'
        r"(?<![\w.])(\$?[A-Za-z]{1,3})(\$?)([1-9]\d*)(?![\w(!])"
    )

    def translate(match: re.Match[str]) -> str:
        column, absolute_row, row = match.groups()
        if column is None or absolute_row:
            return match.group(0)
        new_row = int(row) + row_offset
        if new_row < 1:
            raise ValueError("수식의 상대 행 참조를 1행 이전으로 이동할 수 없습니다.")
        return f"{column}{new_row}"

    return tokens.sub(translate, formula)


def sort_sheet_rows(rows_data, renumber_desc=False, course="web1"):
    """13열 성적 데이터를 4단계 표준 정렬 순서로 정렬합니다:

    1차: week 역순 (descending)
    2차: Type1 오름차순 (ascending)
    3차: Type2 오름차순 (ascending)
    4차: ID 오름차순 (ascending)

    ⚠️ No(A열)는 고유 식별 번호이므로 기본적으로 정렬 시 재부여하지 않고 원본 값을 보존합니다.
    결과를 헤더 다음 2행부터 기록할 수 있도록 E열/K열 수식의 상대 행 참조를 이동합니다.
    """
    normalized = [
        (row_num, normalize_row_to_13cols(r, row_num=row_num, course=course))
        for row_num, r in enumerate(rows_data, start=2)
    ]

    def _sort_key(row):
        # 1) week 역순
        wk_str = str(row[1]).strip() if len(row) > 1 else ""
        try:
            wk_val = -int(wk_str)
        except ValueError:
            wk_val = 0

        # 2) type1 오름차순 (신규 G열, col index 6)
        t1_str = str(row[6]).strip().lower() if len(row) > 6 else ""

        # 3) type2 오름차순 (신규 H열, col index 7)
        t2_str = (
            str(row[7]).replace("과제", "").replace("'", "").strip().lower()
            if len(row) > 7
            else ""
        )

        # 4) id 오름차순 (C열, col index 2)
        id_str = str(row[2]).replace("'", "").strip() if len(row) > 2 else ""
        try:
            id_val = (0, int(id_str))
        except ValueError:
            id_val = (1, id_str) if id_str else (2, "")

        return (wk_val, t1_str, t2_str, id_val)

    sorted_list = []
    for row_num, (original_row_num, row) in enumerate(
        sorted(normalized, key=lambda item: _sort_key(item[1])), start=2
    ):
        offset = row_num - original_row_num
        row[4] = _translate_formula_rows(str(row[4]), offset)
        row[10] = _translate_formula_rows(str(row[10]), offset)
        sorted_list.append(row)

    if renumber_desc:
        total = len(sorted_list)
        for idx, r in enumerate(sorted_list):
            r[0] = str(total - idx)

    return sorted_list


def sort_sheet_remote(course="py"):
    """구글 시트 네이티브 sortRange API를 호출하여 시트 데이터를 정렬한다.

    정렬 기준:
      1차 주차(B열, col 1) 역순
      2차 Type1(G열, col 6) 오름차순
      3차 Type2(H열, col 7) 오름차순
      4차 학번(C열, col 2) 오름차순

    ⚠️ A열(No)을 포함한 전체 행이 원자적으로 이동하므로,
       기존 번호(No) 및 수식(E열, K열)이 절대 훼손되거나 덮어써지지 않고 100% 보존됩니다.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_course_config(base_dir, course)
    if not config:
        print(f"❌ 오류: settings.json에 '{course}' 과정 설정 없음")
        return False

    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")
    if not spreadsheet_id or target_gid is None:
        print(f"❌ 오류: '{course}' sheet_id 또는 target_gid 없음")
        return False

    service = get_sheet_service(base_dir)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)
    if not sheet_title:
        print(f"❌ 오류: gid={target_gid} 시트를 찾을 수 없음")
        return False

    sort_request = {
        "sortRange": {
            "range": {
                "sheetId": target_gid,
                "startRowIndex": 1,  # 헤더(1행) 제외
                "startColumnIndex": 0,  # A열부터 전체 컬럼
            },
            "sortSpecs": [
                {"dimensionIndex": 1, "sortOrder": "DESCENDING"},  # wk (B열)
                {"dimensionIndex": 6, "sortOrder": "ASCENDING"},  # Type1 (G열)
                {"dimensionIndex": 7, "sortOrder": "ASCENDING"},  # Type2 (H열)
                {"dimensionIndex": 2, "sortOrder": "ASCENDING"},  # ID (C열)
            ],
        }
    }

    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [sort_request]},
        ).execute()
        print(
            f"✅ {sheet_title} 네이티브 정렬 완료 (주차 역순 → 학번 오름차순, 원본 No 보존)"
        )
        return True
    except Exception as e:
        print(f"❌ {sheet_title} 정렬 실패: {e}")
        return False


def append_grades_to_sheet(rows_data, course="py"):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # course가 "web"으로 지정된 경우, 1반(web1)과 2반(web2)으로 자동 분기하여 각각의 시트에 기록
    if course == "web":
        web1_rows, web2_rows = route_web_rows(rows_data)
        success = True
        if web1_rows:
            print(
                f"📦 [웹 1반(web1)] {len(web1_rows)}개 행을 1반 시트로 분기 추가합니다."
            )
            if not append_grades_to_sheet(web1_rows, course="web1"):
                success = False
        if web2_rows:
            print(
                f"📦 [웹 2반(web2)] {len(web2_rows)}개 행을 2반 시트로 분기 추가합니다."
            )
            if not append_grades_to_sheet(web2_rows, course="web2"):
                success = False
        return success

    config = load_course_config(base_dir, course)

    if not config:
        print(f"❌ 오류: settings.json에 '{course}' 과정에 대한 설정이 없습니다.")
        return False

    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")

    if not spreadsheet_id or target_gid is None:
        print(
            f"❌ 오류: '{course}' 과정의 sheet_id 또는 target_gid가 올바르지 않습니다."
        )
        return False

    service = get_sheet_service(base_dir)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)

    if not sheet_title:
        print(f"❌ 오류: 시트 ID(gid={target_gid})를 찾을 수 없습니다.")
        return False

    # 기존 데이터에서 최대 no 및 기존 행 수 조회
    max_no = get_max_no(service, spreadsheet_id, sheet_title)
    try:
        res = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{sheet_title}!A:A")
            .execute()
        )
        existing_row_count = len(res.get("values", []))
    except Exception:
        existing_row_count = max_no + 1

    formatted_rows = []
    for i, r in enumerate(rows_data):
        target_row_num = existing_row_count + i + 1
        row = normalize_row_to_13cols(r, row_num=target_row_num, course=course)
        row[0] = max_no + i + 1

        # '주차(wk)' 컬럼(인덱스 1)에 대해, 항상 숫자(int)로 저장하여 정렬 일관성 보장
        if len(row) > 1 and row[1]:
            try:
                row[1] = int(str(row[1]).strip().replace("'", ""))
            except ValueError:
                pass

        # '학번(ID)' 컬럼(인덱스 2)에 대해, 끝 3자리만 추출 + 문자열 강제 포맷팅(') 적용
        if len(row) > 2 and row[2]:
            clean_id = str(row[2]).lstrip("'").strip()
            last3 = clean_id[-3:] if len(clean_id) >= 3 else clean_id
            row[2] = f"'{last3}"

        # 'Track' 컬럼(인덱스 3)에 대해, '1', '2', '4' 단일 숫자로 정규화
        if len(row) > 3 and row[3]:
            row[3] = normalize_track(row[3])

        # E열(Scaled Score): 수식 보장
        row[4] = make_scaled_score_formula(target_row_num)

        # F열 원점수 (Score, 인덱스 5):
        # - 실습 과제(lab): score 탭에는 루브릭 만점 점수(원점수: 9점, 10점 등) 그대로 기록
        # - 이메일 과제(hw) 및 기타: 1.0점 만점 스케일 적용 (SSOT 정책 준수)
        if len(row) > 5 and row[5] != "":
            t1_val = row[6] if len(row) > 6 else ""
            t2_val = row[7] if len(row) > 7 else ""
            if is_lab_assignment(t1_val, t2_val):
                pass
            else:
                row[5] = convert_score_to_1scale(str(row[5]))
            try:
                row[5] = float(row[5])
            except (ValueError, TypeError):
                pass

        # 'Type2' 컬럼(인덱스 7)에 대해 문자열 강제 포맷팅(') 적용
        if len(row) > 7 and row[7]:
            clean_type2 = str(row[7]).replace("과제", "").replace("'", "").strip()
            row[7] = f"'{clean_type2}"

        # 사유 SSOT 정규화 (인덱스 8)
        if len(row) > 8 and row[8]:
            row[8] = normalize_reason_to_ssot(str(row[8]))

        # Date 포맷팅 (인덱스 9): mm/dd hh:mm 형식 보장
        if len(row) > 9 and row[9]:
            row[9] = format_date_to_mmdd_hhmm(row[9])

        # K열(Name, 인덱스 10): VLOOKUP 수식 보장
        row[10] = make_name_vlookup_formula(target_row_num, course=course)

        # 'Subject' 컬럼(인덱스 11) 문자열 포맷팅
        if len(row) > 11 and row[11]:
            clean_subject = str(row[11]).lstrip("'")
            row[11] = f"'{clean_subject}"

        # 분반별 언어 정책: 파이썬(K트랙)은 한글, 웹(E트랙)은 영어
        if course == "py" and len(row) > 8:
            row[8] = translate_reason_to_ko(str(row[8]))
        elif course in ["web", "web1", "web2"] and len(row) > 8:
            row[8] = translate_reason_to_en(str(row[8]))

        formatted_rows.append(row[:13])

    range_name = f"{sheet_title}!A:M"  # A~M열 13열 데이터 기준으로 append
    body = {"values": formatted_rows}

    print(
        f"📝 구글 시트 '{sheet_title}' 탭에 {len(formatted_rows)}개의 데이터 추가를 시도합니다..."
    )

    try:
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

        updates = result.get("updates", {})
        updated_rows = updates.get("updatedRows", 0)
        print(
            f"✅ 구글 시트 업데이트 완료: 성공적으로 {updated_rows}개 행이 추가되었습니다!"
        )
        # 시트 서식 적용
        apply_score_sheet_formatting(service, spreadsheet_id, target_gid)
        return True

    except Exception as e:
        print(f"❌ 구글 시트 업데이트 실패: {e}")
        return False


def upsert_grades_to_sheet(rows_data, course="py"):
    """(StudentID, Type1, Type2) 복합 키를 기준으로 멱등성(Idempotency)을 보장하는 Upsert 함수.

    - 기존 행에 동일한 (학번, 대분류, 세부유형)이 존재하면 해당 행을 갱신(Update).
    - 존재하지 않으면 최하단에 신규 추가(Append).
    - 스크립트를 N번 실행해도 중복 데이터가 누적되지 않음.
    - E열(환산점수 수식) 및 K열(Name VLOOKUP 수식)을 절대 덮어쓰지 않고 보존함.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # course가 "web"으로 지정된 경우, 1반(web1)과 2반(web2)으로 자동 분기하여 각각 멱등 동기화
    if course == "web":
        web1_rows, web2_rows = route_web_rows(rows_data)
        success = True
        if web1_rows:
            print(
                f"📦 [웹 1반(web1)] {len(web1_rows)}개 행을 1반 시트로 멱등 동기화합니다."
            )
            if not upsert_grades_to_sheet(web1_rows, course="web1"):
                success = False
        if web2_rows:
            print(
                f"📦 [웹 2반(web2)] {len(web2_rows)}개 행을 2반 시트로 멱등 동기화합니다."
            )
            if not upsert_grades_to_sheet(web2_rows, course="web2"):
                success = False
        return success

    config = load_course_config(base_dir, course)

    if not config:
        print(f"❌ 오류: settings.json에 '{course}' 과정에 대한 설정이 없습니다.")
        return False

    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")

    if not spreadsheet_id or target_gid is None:
        print(
            f"❌ 오류: '{course}' 과정의 sheet_id 또는 target_gid가 올바르지 않습니다."
        )
        return False

    service = get_sheet_service(base_dir)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)

    if not sheet_title:
        print(f"❌ 오류: 시트 ID(gid={target_gid})를 찾을 수 없습니다.")
        return False

    # 기존 시트의 전체 데이터 읽기 (2행부터 A~M, 수식을 유지하기 위해 valueRenderOption="FORMULA" 필수)
    range_all = f"{sheet_title}!A2:M"
    try:
        res = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=range_all,
                valueRenderOption="FORMULA",
            )
            .execute()
        )
        existing_rows = res.get("values", [])
    except Exception as e:
        print(f"⚠️ 기존 데이터 조회 실패: {e}")
        existing_rows = []

    # 기존 행 중 E열(Scaled Score) 또는 K열(Name VLOOKUP) 수식이 누락된 행 일괄 보정
    missing_formula_updates = []
    for idx, r in enumerate(existing_rows):
        r_num = idx + 2
        if len(r) > 1 and str(r[1]).strip():
            # E열(Scaled Score) 수식 점검
            if len(r) <= 4 or not str(r[4]).strip().startswith("="):
                formula_scaled = make_scaled_score_formula(r_num)
                missing_formula_updates.append(
                    {"range": f"{sheet_title}!E{r_num}", "values": [[formula_scaled]]}
                )
            # K열(Name) VLOOKUP 수식 점검
            if len(r) <= 10 or not str(r[10]).strip().startswith("="):
                formula_name = make_name_vlookup_formula(r_num, course=course)
                missing_formula_updates.append(
                    {"range": f"{sheet_title}!K{r_num}", "values": [[formula_name]]}
                )

    if missing_formula_updates:
        try:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": missing_formula_updates,
                },
            ).execute()
            print(
                f"🔧 수식(E열 환산점수 / K열 Name VLOOKUP) 누락 {len(missing_formula_updates)}개 셀 자동 보정 완료"
            )
        except Exception as e:
            print(f"⚠️ 수식 자동 보정 실패: {e}")

    # 기존 데이터 인덱싱: (student_id_last3, type1, type2) -> row_number (idx + 2)
    def _normalize_sid(raw: str) -> str:
        """학번 문자열을 끝 3자리로 정규화 (키 비교 전용)."""
        clean = str(raw).replace("'", "").strip()
        return clean[-3:] if len(clean) >= 3 else clean

    key_to_row_num = {}
    for idx, row in enumerate(existing_rows):
        # 13열 기준: ID=2, Type1=6, Type2=7
        if len(row) > 7:
            sid = _normalize_sid(row[2])
            t1 = str(row[6]).strip()
            t2 = str(row[7]).replace("과제", "").replace("'", "").strip()
            key_to_row_num[(sid, t1, t2)] = idx + 2
        elif len(row) > 6:  # 구 11열 기준 호환: ID=2, Type1=5, Type2=6
            sid = _normalize_sid(row[2])
            t1 = str(row[5]).strip()
            t2 = str(row[6]).replace("과제", "").replace("'", "").strip()
            key_to_row_num[(sid, t1, t2)] = idx + 2
        elif len(row) > 4:  # 구 9열 기준 호환: ID=1, Type=4
            sid = _normalize_sid(row[1])
            t1 = "hw"
            t2 = str(row[4]).replace("과제", "").replace("'", "").strip()
            key_to_row_num[(sid, t1, t2)] = idx + 2

    rows_to_update = []  # (row_number, formatted_row)
    rows_to_append = []

    max_no = get_max_no(service, spreadsheet_id, sheet_title)

    for r_in in rows_data:
        row = normalize_row_to_13cols(r_in, course=course)

        # 주차(wk) 컬럼(인덱스 1)에 대해 숫자(int) 보장
        if len(row) > 1 and row[1]:
            try:
                row[1] = int(str(row[1]).strip().replace("'", ""))
            except ValueError:
                pass

        # ID 포맷팅 (인덱스 2): 끝 3자리 추출 + 문자열 강제 포맷팅(') 적용
        if len(row) > 2 and row[2]:
            clean_id = str(row[2]).lstrip("'").strip()
            last3 = clean_id[-3:] if len(clean_id) >= 3 else clean_id
            row[2] = f"'{last3}"
        else:
            clean_id = ""

        # 'Track' 컬럼(인덱스 3)에 대해, '1', '2', '4' 단일 숫자로 정규화
        if len(row) > 3 and row[3]:
            row[3] = normalize_track(row[3])

        sid_key = _normalize_sid(clean_id)

        # Type1 (인덱스 6)
        t1 = str(row[6]).strip() if len(row) > 6 and row[6] else "hw"
        row[6] = t1

        # Type2 포맷팅 (인덱스 7)
        if len(row) > 7 and row[7]:
            clean_type2 = str(row[7]).replace("과제", "").replace("'", "").strip()
            row[7] = f"'{clean_type2}"
        else:
            clean_type2 = ""

        # F열 원점수 (Score, 인덱스 5)
        if len(row) > 5 and row[5] != "":
            if is_lab_assignment(t1, clean_type2):
                pass
            else:
                row[5] = convert_score_to_1scale(str(row[5]))
            try:
                row[5] = float(row[5])
            except (ValueError, TypeError):
                pass

        # Date 포맷팅 (인덱스 9): mm/dd hh:mm 형식 보장
        if len(row) > 9 and row[9]:
            row[9] = format_date_to_mmdd_hhmm(row[9])

        # 사유 SSOT 정규화 (인덱스 8)
        if len(row) > 8 and row[8]:
            row[8] = normalize_reason_to_ssot(str(row[8]))

        # 분반별 언어 정책: 파이썬(K트랙)은 한글, 웹(E트랙)은 영어
        if course == "py" and len(row) > 8:
            row[8] = translate_reason_to_ko(str(row[8]))
        elif course in ["web", "web1", "web2"] and len(row) > 8:
            row[8] = translate_reason_to_en(str(row[8]))

        # Subject 포맷팅 (인덱스 11)
        if len(row) > 11 and row[11]:
            clean_subject = str(row[11]).lstrip("'")
            row[11] = f"'{clean_subject}"

        key = (sid_key, t1, clean_type2)

        while len(row) < 13:
            row.append("")

        if key in key_to_row_num:
            # 기존 행 갱신 (No 유지, E열 수식 보존, K열 수식 보존, M열 Appeal 보존)
            existing_row_num = key_to_row_num[key]
            existing_row_idx = existing_row_num - 2
            existing_data = (
                existing_rows[existing_row_idx]
                if 0 <= existing_row_idx < len(existing_rows)
                else []
            )
            existing_no = (
                existing_data[0]
                if len(existing_data) > 0 and existing_data[0] != ""
                else row[0]
            )
            existing_scaled = (
                existing_data[4]
                if (len(existing_data) > 4 and str(existing_data[4]).startswith("="))
                else make_scaled_score_formula(existing_row_num)
            )
            existing_name = (
                existing_data[10]
                if (len(existing_data) > 10 and str(existing_data[10]).startswith("="))
                else make_name_vlookup_formula(existing_row_num, course=course)
            )
            existing_appeal = existing_data[12] if len(existing_data) > 12 else ""

            row[0] = existing_no
            row[4] = existing_scaled
            row[10] = existing_name
            row[12] = existing_appeal

            rows_to_update.append((existing_row_num, row[:13]))
        else:
            # 신규 추가 (13열 구조: E열 수식 주입, K열 VLOOKUP 수식 주입, M열 빈칸)
            max_no += 1
            row[0] = max_no
            new_append_row_num = len(existing_rows) + 2 + len(rows_to_append)
            row[4] = make_scaled_score_formula(new_append_row_num)
            row[10] = make_name_vlookup_formula(new_append_row_num, course=course)
            row[12] = ""
            rows_to_append.append(row[:13])
            # 같은 배치 내 중복 방지
            key_to_row_num[key] = -1

    success = True

    # 1. 기존 행 멱등 갱신 (Update: A~M)
    for row_num, row_data_13 in rows_to_update:
        try:
            update_range = f"{sheet_title}!A{row_num}:M{row_num}"
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body={"values": [row_data_13]},
            ).execute()
        except Exception as e:
            print(f"⚠️ 행 {row_num} 갱신 실패: {e}")
            success = False

    if rows_to_update:
        print(f"🔄 멱등 갱신 완료: {len(rows_to_update)}개 기존 행 업데이트됨")

    # 2. 신규 행 추가 (Append: A~M)
    if rows_to_append:
        try:
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_title}!A:M",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows_to_append},
            ).execute()
            print(f"➕ 신규 추가 완료: {len(rows_to_append)}개 신규 행 추가됨")
        except Exception as e:
            print(f"❌ 신규 행 추가 실패: {e}")
            success = False

    # 3. 신규 행이 추가된 경우 자동 re-sort (정렬 일관성 보장)
    if rows_to_append and success:
        print("🔄 신규 행 추가에 따른 자동 정렬 실행 중...")
        try:
            sort_sheet_remote(course=course)
        except Exception as e:
            print(f"⚠️ 자동 정렬 실패 (데이터는 정상 기록됨): {e}")

    # 4. 시트 서식 적용 (Score/Scaled Score 우측 정렬, Date 왼쪽 정렬)
    if success:
        apply_score_sheet_formatting(service, spreadsheet_id, target_gid)

    return success
