#!/usr/bin/env python3
"""
bin/grade_photos.py — 구글 포토 앨범 사진 제출 채점 스크립트

분반별 구글 포토 공유 앨범을 파싱하여 제출자(1.0점) / 미제출자(0.0점)를
각 분반 성적 시트의 score 탭에 type=0.p 로 upsert 기록합니다.

Usage:
    .venv/bin/python3 bin/grade_photos.py [--dry-run] [--course web1|web2|py|all]
"""

import os
import re
import sys
import json
import argparse
import datetime
import urllib.request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import upsert_grades_to_sheet

# ──────────────────────────────────────────────────────────────────────
# 앨범 URL (SSOT: 1docs/sheets.md)
# ──────────────────────────────────────────────────────────────────────
ALBUM_URLS = {
    "web1": "https://photos.app.goo.gl/hSLMuNdzZoudgxTx5",
    "web2": "https://photos.app.goo.gl/yCfTZRmmRdKZg8sj9",
    "py": "https://photos.app.goo.gl/6ysLMegsr4Ro6WV58",
}

# ──────────────────────────────────────────────────────────────────────
# 구글 계정 이름 → 수강생 공식이름 별칭 매핑
# (분반 구분 없이 통합 관리. 동명이인은 없음)
# ──────────────────────────────────────────────────────────────────────
UPLOADER_ALIASES: dict[str, str] = {
    # Web1 aliases
    "Lotus Bastola": "BASTOLA KAMAL",
    "Samuel Ghouri": "PERVAIZ SAMUEL",
    "Aur Joon": "KAFLE ARJUN",
    "Deepan Kafle": "KAFLE DIPAN PRASAD",
    "Bipin": "KHULAL BIPIN",
    "Dipesh Sanjyal": "JAISHI DIPESH RAJ",
    "Coding Course": "PERVAIZ SAMUEL",  # 수업용 계정 = Samuel
    "Kaleydon": "RAUT KIRAN",  # ← 교수님이 판단 필요
    # Web2 aliases
    "Rabin Bista": "BISTA RAVINDRA KUMAR",
    "Pakriti Nepal": "NEPAL PRAKRITI",
    "Joya Khatiwada": "DOTEL JAYA LAXMI",
    "Ramesh Jaishi": "JAISHI ROMAN",
    "Yoanesh Subba": "SUBBA YOUNESH",
    "Saimoni stha": "SHRESTHA SAIMONAI",
    "Riza Thapa Mgr": "THAPA RIZA",
    "Prabin Magar": "GHARTI MAGAR PRABIN",
    "Karun Ramdam": "BISHOWAKARMA KARUN",
    "Sumit Sarraf": "SARRAF SUMIT KUMAR",
    "Sumit sarraf Stu": "SARRAF SUMIT KUMAR",
    "KB Gamer": "BHANDARI KAILASH",  # ← 교수님이 판단 필요
    "Anish Geere": "BAM SHUDIKSHA",  # ← 교수님이 판단 필요 (web2 업로더인데 web1 학생)
    # Py4 aliases (Vietnamese/Myanmar)
    "Nguyễn Thị Cẩm Nguyên": "NGUYEN THI CAM NGUYEN",
    "Trang Nguyễn": "NGUYEN THI THU TRANG",
    "Sơn Lê Khắc": "LE KHAC SON",
    "Linh Nguyễn": "NGUYEN THI THUY LINH",
    "Đô Trần": "TRAN VAN DO",
    "Diễn Nguyễn": "NGUYEN QUOC DIEN",
    "Phương Phạm Tiến": "PHAM TIEN PHUONG",
    "Nga Phạm": "PHAM THI NGA",
    "NGUYEN VAN QUY": "NGUYEN VAN QUY",
}

# ──────────────────────────────────────────────────────────────────────
# 학생 명단 파서
# ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_students(course: str) -> list[dict]:
    """
    course: 'web1' | 'web2' | 'py'
    Returns list of {sid, name, course_id}
    """
    if course in ("web1", "web2"):
        md_path = os.path.join(BASE_DIR, "5input/students/wb-students.md")
        target_code = "15143" if course == "web1" else "15144"
    else:
        md_path = os.path.join(BASE_DIR, "5input/students/py-students.md")
        target_code = "14712"

    students = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 9 and parts[3].isdigit() and parts[1] == target_code:
                students.append({"sid": parts[3], "name": parts[4]})
    return students


# ──────────────────────────────────────────────────────────────────────
# 구글 포토 앨범 파서 (AF_initDataCallback 방식)
# ──────────────────────────────────────────────────────────────────────


def _fetch_album_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_uploaders(album_url: str) -> set[str]:
    """앨범에서 사진을 업로드한 사람들의 구글 계정 이름 집합을 반환 (교수 제외)."""
    html = _fetch_album_html(album_url)

    callbacks = re.findall(r"AF_initDataCallback\((.*?)\);</script>", html, re.DOTALL)
    if len(callbacks) < 2:
        raise ValueError(f"앨범 파싱 실패: callback 부족 ({len(callbacks)}개)")

    m_data = re.search(r"data:\s*(\[.*\])\s*,\s*sideChannel:", callbacks[1], re.DOTALL)
    if not m_data:
        raise ValueError("앨범 데이터 파싱 실패")

    data = json.loads(m_data.group(1))
    photos = data[1]
    users_list = data[3][9]

    user_map: dict[str, str] = {}
    for u in users_list:
        uid = u[0]
        name = u[11][0] if len(u) > 11 and u[11] else (u[2] if len(u) > 2 else None)
        if name:
            user_map[uid] = name

    uploaders: set[str] = set()
    for p in photos:
        uid = p[6][0] if len(p) > 6 and p[6] else None
        name = user_map.get(uid) if uid is not None else None
        if name and name != "정원혁":
            uploaders.add(name)

    return uploaders


# ──────────────────────────────────────────────────────────────────────
# 이름 매칭 (uploader_name → 공식 student name)
# ──────────────────────────────────────────────────────────────────────


def resolve_uploader(uploader_name: str, students: list[dict]) -> str | None:
    """uploader 이름을 공식 수강생 이름(name)으로 변환. 없으면 None."""
    # 1. 별칭 매핑
    official = UPLOADER_ALIASES.get(uploader_name)
    if official:
        # student 목록에 있는지 확인
        for s in students:
            if s["name"] == official:
                return official
        return None  # 이 분반 소속 아님

    # 2. 직접 이름 매칭 (대소문자 무시)
    u_words = set(uploader_name.lower().split())
    best_match = None
    best_score = 0
    for s in students:
        s_words = set(s["name"].lower().split())
        inter = u_words & s_words
        if len(inter) > best_score or (
            len(inter) == best_score and inter and any(len(w) > 3 for w in inter)
        ):
            best_score = len(inter)
            best_match = s["name"]

    if best_score >= 2:
        return best_match
    if best_score == 1 and best_match is not None:
        common = next(iter(u_words & set(best_match.lower().split())))
        if len(common) > 4:
            return best_match

    return None


# ──────────────────────────────────────────────────────────────────────
# 채점 결과 생성
# ──────────────────────────────────────────────────────────────────────


def build_score_rows(
    course: str,
    students: list[dict],
    uploaders: set[str],
    today: str,
) -> list[list]:
    """
    채점 결과 행 생성.
    E트랙(web1/web2): 영어 표기
    K트랙(py): 한국어 표기
    """
    is_korean = course == "py"

    # uploader → student name 매핑
    matched_students: set[str] = set()
    unresolved_uploaders: list[str] = []

    for u in uploaders:
        resolved = resolve_uploader(u, students)
        if resolved:
            matched_students.add(resolved)
        else:
            unresolved_uploaders.append(u)

    if unresolved_uploaders:
        print(f"  ⚠️  매칭 실패 업로더 (무시됨): {unresolved_uploaders}")

    rows = []
    for s in students:
        sid_short = s["sid"][-3:]  # 학번 뒤 3자리 (기존 시트 형식)
        name = s["name"]
        submitted = name in matched_students

        score = "1.00" if submitted else "0.00"

        if is_korean:
            track = "4"
            reason = "포토 앨범 제출" if submitted else "미제출"
            subject = "구글 포토 앨범"
        else:
            track_code = "1" if course == "web1" else "2"
            track = track_code
            reason = (
                "Photo submitted to Google Photos album"
                if submitted
                else "Not submitted"
            )
            subject = "Google Photos Album"

        # 컬럼 순서: no, wk, sid, track, score, type1, type2, reason, date, name, subject (A~K, 11열)
        row = [
            "",  # no (upsert 시 자동 부여)
            "1",  # wk (0.p = 1주차 프로필 사진 과제)
            sid_short,
            track,
            score,
            "hw",
            "0.p",
            reason,
            today,
            name,
            subject,
        ]
        rows.append(row)

    return rows


# ──────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────


def grade_course(course: str, dry_run: bool) -> None:
    today = datetime.date.today().strftime("%-m/%-d")
    url = ALBUM_URLS[course]

    print(f"\n{'='*60}")
    print(f"[{course.upper()}] 구글 포토 앨범 채점 시작")
    print(f"  앨범 URL: {url}")
    print(f"  날짜: {today}")

    print("  앨범 파싱 중...")
    try:
        uploaders = extract_uploaders(url)
    except Exception as e:
        print(f"  ❌ 앨범 파싱 실패: {e}")
        return

    students = load_students(course)
    print(f"  수강생: {len(students)}명 | 앨범 업로더: {len(uploaders)}명")

    rows = build_score_rows(course, students, uploaders, today)

    # dry-run 출력 (11열 기준: 인덱스 4=score, 2=sid, 7=reason)
    submitted = [r for r in rows if r[4] == "1.00"]
    not_submitted = [r for r in rows if r[4] == "0.00"]
    print(f"\n  ✅ 제출: {len(submitted)}명")
    for r in submitted:
        print(f"    {r[2]} {r[7]}")
    print(f"\n  ❌ 미제출: {len(not_submitted)}명")
    for r in not_submitted:
        print(f"    {r[2]} {r[7]}")

    if dry_run:
        print("\n  [DRY-RUN] 시트에 반영하지 않습니다.")
        return

    print("\n  시트에 반영 중...")
    upsert_grades_to_sheet(rows, course=course)


def main() -> None:
    parser = argparse.ArgumentParser(description="구글 포토 앨범 사진 제출 채점")
    parser.add_argument(
        "--course",
        choices=["web1", "web2", "py", "all"],
        default="all",
        help="채점 대상 분반 (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="시트에 실제로 기록하지 않고 결과만 출력",
    )
    args = parser.parse_args()

    courses = ["web1", "web2", "py"] if args.course == "all" else [args.course]

    for course in courses:
        grade_course(course, dry_run=args.dry_run)

    print("\n모든 채점 완료.")


if __name__ == "__main__":
    main()
