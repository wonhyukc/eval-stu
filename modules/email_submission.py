"""학생 원본 메시지 식별과 발송 시각 파싱 (브라우저 의존 없음)."""

import email.utils
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

KST = timezone(timedelta(hours=9))
INSTRUCTOR_EMAIL = "wonhyukc@stu.ac.kr"


class OriginalSubmissionError(ValueError):
    """원본 메시지를 확인할 수 없어 자동 채점을 진행할 수 없음."""


def _is_valid_http_url(raw: str) -> bool:
    """통신 없이 HTTP(S) 주소의 호스트·포트 형식을 확인한다."""
    if re.search(r"[\s<>\"']", raw):
        return False
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").encode("idna").decode("ascii")
        return bool(
            parsed.scheme in {"http", "https"}
            and host
            and re.fullmatch(r"[A-Za-z0-9._:-]+", host)
            and (parsed.port is None or 0 < parsed.port <= 65535)
        )
    except (ValueError, UnicodeError):
        return False


class _PureBodyParser(HTMLParser):
    """Gmail 인용 영역을 건너뛰고 표시 본문과 학생 링크만 모은다."""

    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    BLOCK_TAGS = {"br", "div", "p", "li", "tr", "pre", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.quote_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        ignored = tag in {"blockquote", "script", "style"} or bool(
            classes & {"gmail_quote", "gmail_attr"}
        )
        if self.quote_depth or ignored:
            if tag not in self.VOID_TAGS:
                self.quote_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        href = attributes.get("href") or ""
        if tag == "a" and _is_valid_http_url(href):
            self.parts.append(f" {href} ")

    def handle_endtag(self, tag):
        if tag in self.VOID_TAGS:
            return
        if self.quote_depth:
            self.quote_depth -= 1
        if not self.quote_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.quote_depth:
            self.parts.append(data)


def extract_pure_body(body_html: str) -> str:
    """HTML 인용 영역과 텍스트 인용·회신 헤더 이후 내용을 제거한다."""
    parser = _PureBodyParser()
    parser.feed(body_html)
    parser.close()
    return strip_gmail_quotes("".join(parser.parts))


def strip_gmail_quotes(body: str) -> str:
    """Gmail 인용구와 회신 헤더를 제거한다."""
    lines = []
    pattern_en = re.compile(r"^On .* wrote:$", re.IGNORECASE)
    pattern_ko = re.compile(r"^On .*에 .* 작성:$")
    for line in body.splitlines():
        clean = line.strip()
        # issue #133: Check for Gmail reply block
        if (
            pattern_en.match(clean)
            or pattern_ko.match(clean)
            or re.match(
                r"(?:wrote:|.*đã viết:|.*(?:님이|님께서)\s*작성:|작성:)$",
                clean,
                flags=re.IGNORECASE,
            )
        ):
            break
        if clean.startswith(">"):
            continue
        lines.append(clean)
    return "\n".join(lines).strip()


def has_valid_submission_body(body_html: str) -> bool:
    """인용문 제외 공백 없이 30자 이상이거나 유효한 HTTP(S) 링크가 있어야 한다."""
    pure = extract_pure_body(body_html)
    if len(re.sub(r"\s+", "", pure)) >= 30:
        return True
    return any(
        _is_valid_http_url(url.rstrip(".,;!?"))
        for url in re.findall(r"https?://[^\s<>\"']+", pure, flags=re.IGNORECASE)
    )


def parse_submission_datetime(raw: str) -> datetime | None:
    """날짜와 시각이 있는 Gmail 상세 타임스탬프만 KST로 변환한다."""
    raw = raw.strip()
    if not re.search(r"\d{1,2}:\d{2}", raw):
        return None

    korean = re.fullmatch(
        r"(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일.*?"
        r"(오전|오후)\s*(\d{1,2}):(\d{2})(?::(\d{2}))?",
        raw,
    )
    if korean:
        year, month, day, am_pm, hour, minute, second = korean.groups()
        try:
            hour_num = int(hour)
            if not 1 <= hour_num <= 12:
                return None
            hour_num = hour_num % 12 + (12 if am_pm == "오후" else 0)
            return datetime(
                int(year) if year else datetime.now(KST).year,
                int(month),
                int(day),
                hour_num,
                int(minute),
                int(second or 0),
                tzinfo=KST,
            )
        except ValueError:
            return None

    # RFC 파서는 Gmail 영문 표시의 AM/PM을 무시하므로 별도로 처리한다.
    if re.search(r"\b(?:AM|PM)\b", raw, re.IGNORECASE):
        clean = re.sub(
            r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        )
        clean = re.sub(r"[,\s]+", " ", clean).strip()
        for month_format in ("%b", "%B"):
            for time_format in ("%I:%M %p", "%I:%M:%S %p"):
                try:
                    return datetime.strptime(
                        clean, f"{month_format} %d %Y {time_format}"
                    ).replace(tzinfo=KST)
                except ValueError:
                    pass
        return None

    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return (
            parsed.replace(tzinfo=KST)
            if parsed.tzinfo is None
            else parsed.astimezone(KST)
        )
    except (ValueError, TypeError, OverflowError):
        return None


def select_latest_submission(
    submissions: list[dict[str, Any]], grace_deadline: datetime | None
) -> dict[str, Any] | None:
    """유예마감 이전 최신본을 우선하고, 없으면 마감 이후 최신본을 선택한다."""
    if not submissions:
        return None
    for submission in submissions:
        sent_at = submission.get("sent_at")
        if not isinstance(sent_at, datetime) or sent_at.tzinfo is None:
            raise OriginalSubmissionError("학생 원본 발송 시각을 확인할 수 없습니다.")
    on_time = (
        [s for s in submissions if s["sent_at"] < grace_deadline]
        if grace_deadline is not None
        else []
    )
    return max(on_time or submissions, key=lambda s: s["sent_at"])


def deduplicate_submissions(
    submissions: list[dict[str, Any]], grace_deadline: datetime
) -> list[dict[str, Any]]:
    """학생·과제별로 모은 원본 시각을 비교해 제출본을 선택한다. 점수는 비교하지 않는다."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    unidentified = []
    for submission in submissions:
        sid = str(submission.get("student_id") or "").replace("'", "").strip()
        task = str(submission.get("task_id") or "").strip()
        if not sid or not task:
            unidentified.append(submission)
            continue
        key = (sid[-3:], task)
        grouped.setdefault(key, []).append(submission)
    selected = [
        select_latest_submission(rows, grace_deadline) for rows in grouped.values()
    ]
    return [s for s in selected if s is not None] + unidentified


def select_original_submission(
    messages: list[dict[str, str]],
    grace_deadline: datetime | None = None,
    start_time: datetime | None = None,
) -> dict[str, Any] | None:
    """교수 답장을 제외하고 학생 원본 시각 기준 유효 제출본을 반환한다."""
    is_replied = any(
        m.get("sender_email", "").strip().lower() == INSTRUCTOR_EMAIL for m in messages
    )
    submissions = []
    for message in messages:
        sender = message.get("sender_email", "").strip().lower()
        if sender == INSTRUCTOR_EMAIL:
            continue
        if not sender:
            raise OriginalSubmissionError("원본 메시지 발신자를 확인할 수 없습니다.")
        sent_at = parse_submission_datetime(message.get("date_str", ""))
        if sent_at is None:
            raise OriginalSubmissionError("학생 원본 발송 시각을 확인할 수 없습니다.")
        if start_time is not None and sent_at < start_time:
            continue
        submissions.append({**message, "sent_at": sent_at, "is_replied": is_replied})
    return select_latest_submission(submissions, grace_deadline)


def generate_missing_submission_rows(
    graded_ids: set[str],
    roster_students: list[dict[str, Any]] | dict[str, dict[str, Any]],
    week: str,
    course: str,
) -> list[list[str]]:
    """미제출자 0점 시트 등록을 위한 행 데이터를 생성한다.

    Reason: No submission / 미제출 등
    """
    rows = []

    if isinstance(roster_students, dict):
        roster_students = list(roster_students.values())

    reason = "미제출" if course == "py" else "No submission"
    task_id = f"0.{week}"

    for student in roster_students:
        s_id = student.get("id") or student.get("student_id")
        if not s_id or s_id in graded_ids:
            continue

        row = [
            "",
            str(week),
            s_id,
            student.get("track", ""),
            "0.00",
            "hw",
            task_id,
            reason,
            "-",
            student.get("eng_name", student.get("name", "")),
            "-",
        ]
        rows.append(row)

    return rows
