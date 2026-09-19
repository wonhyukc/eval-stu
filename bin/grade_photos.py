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

from modules.sheet_updater import (
    get_sheet_service,
    load_course_config,
    get_target_sheet_title,
)

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
# 역순 삽입 upsert (최신 데이터가 헤더 바로 아래 = 맨 위)
# ──────────────────────────────────────────────────────────────────────


def upsert_top_insert(rows_data: list[list], course: str) -> bool:
    """
    기존 시트 데이터를 읽어 (StudentID, Type1, Type2) 키로 upsert.
    - 행 번호는 계속 증가 (기존 행 번호 유지, 신규 행은 max+1부터 순차 부여)
    - 11열 구조 (A~K) 준수
    """
    config = load_course_config(BASE_DIR, course)
    if not config:
        print(f"❌ '{course}' 설정 없음")
        return False

    spreadsheet_id = config.get("sheet_id")
    target_gid = config.get("target_gid")
    if not spreadsheet_id or target_gid is None:
        print(f"❌ '{course}' sheet_id 또는 target_gid 오류")
        return False

    service = get_sheet_service(BASE_DIR)
    sheet_title = get_target_sheet_title(service, spreadsheet_id, target_gid)
    if not sheet_title:
        print(f"❌ gid={target_gid} 탭 없음")
        return False

    # 기존 데이터 읽기 (헤더 제외, A2부터 K까지)
    res = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_title}!A2:K")
        .execute()
    )
    existing_rows: list[list] = res.get("values", [])

    # (sid, type1, type2) → existing_row 인덱스
    key_to_idx: dict[tuple, int] = {}
    for idx, row in enumerate(existing_rows):
        if len(row) > 6:  # 11열 기준: ID=2, Type1=5, Type2=6
            sid = str(row[2]).strip().lstrip("'")
            t1 = str(row[5]).strip()
            ctype = str(row[6]).lstrip("'").replace("과제", "").strip()
            key_to_idx[(sid, t1, ctype)] = idx
        elif len(row) > 4:  # 9열 기준 호환: ID=1, Type=4
            sid = str(row[1]).strip().lstrip("'")
            ctype = str(row[4]).lstrip("'").replace("과제", "").strip()
            key_to_idx[(sid, "hw", ctype)] = idx

    # 현재 최대 번호 파악 (번호는 계속 증가)
    max_no = 0
    for row in existing_rows:
        try:
            no = int(str(row[0]).strip())
            if no > max_no:
                max_no = no
        except (ValueError, IndexError):
            pass

    # 새 행 처리
    new_rows = list(existing_rows)  # 복사

    for row in rows_data:
        # 11열 정규화
        if len(row) == 9:
            (
                no_val,
                sid_val,
                trk_val,
                scr_val,
                typ_val,
                rsn_val,
                dt_val,
                nm_val,
                sbj_val,
            ) = row
            row = [
                no_val,
                "1",
                sid_val,
                trk_val,
                scr_val,
                "hw",
                typ_val,
                rsn_val,
                dt_val,
                nm_val,
                sbj_val,
            ]
        elif len(row) < 11:
            row = list(row) + [""] * (11 - len(row))

        sid = str(row[2]).strip().lstrip("'")
        t1 = str(row[5]).strip()
        clean_type = str(row[6]).lstrip("'").replace("과제", "").strip()
        key = (sid, t1, clean_type)

        # ID 포맷팅
        row[2] = f"'{sid}"
        # Type2 포맷팅 (구글 시트 자동변환 방지)
        row[6] = f"'{clean_type}"
        # Subject 포맷팅
        if len(row) > 10:
            row[10] = f"'{str(row[10]).lstrip(chr(39))}"

        if key in key_to_idx:
            # 기존 행 갱신 (no 유지)
            idx = key_to_idx[key]
            existing_no = new_rows[idx][0] if new_rows[idx] else ""
            row[0] = existing_no
            new_rows[idx] = row
        else:
            # 신규 행: max_no+1부터 순차 부여
            max_no += 1
            row[0] = max_no
            new_rows.append(row)

    if not new_rows:
        print("ℹ️  기록할 데이터 없음")
        return True

    # 번호 내림차순 정렬 (큰 번호 = 최신 = 맨 위)
    def sort_key(r: list) -> int:
        try:
            return -int(str(r[0]).strip())
        except (ValueError, IndexError):
            return 0

    new_rows.sort(key=sort_key)

    added_count = len(new_rows) - len(existing_rows)
    print(
        f"📝 '{sheet_title}' 탭 전체 갱신: {len(new_rows)}행"
        f" (신규 {added_count}행 추가, 번호 {max_no - added_count + 1}~{max_no})"
    )

    # 헤더 이후 전체 덮어쓰기
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_title}!A2:K{len(new_rows) + 1}",
            valueInputOption="USER_ENTERED",
            body={"values": new_rows},
        ).execute()
        print("✅ 완료")
        return True
    except Exception as e:
        print(f"❌ 시트 갱신 실패: {e}")
        return False


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

    # dry-run 출력
    submitted = [r for r in rows if r[3] == "1.00"]
    not_submitted = [r for r in rows if r[3] == "0.00"]
    print(f"\n  ✅ 제출: {len(submitted)}명")
    for r in submitted:
        print(f"    {r[1]} {r[7]}")
    print(f"\n  ❌ 미제출: {len(not_submitted)}명")
    for r in not_submitted:
        print(f"    {r[1]} {r[7]}")

    if dry_run:
        print("\n  [DRY-RUN] 시트에 반영하지 않습니다.")
        return

    print("\n  시트에 반영 중...")
    upsert_top_insert(rows, course)


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
