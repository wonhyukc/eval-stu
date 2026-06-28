import os
import sys
import csv
import re
import argparse
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote
import time
import email.utils
from playwright.sync_api import sync_playwright

# 프로젝트 루트 경로를 sys.path에 추가
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)

KST = timezone(timedelta(hours=9))


def parse_students():
    name_to_id = {}
    id_to_track = {}
    id_to_names = {}
    base_dir = os.path.dirname(os.path.dirname(__file__))
    for filepath in [
        os.path.join(base_dir, "5input/students/py-students.md"),
        os.path.join(base_dir, "5input/students/wb-students.md"),
        os.path.join(base_dir, "input/students/py-students.md"),
        os.path.join(base_dir, "input/students/wb-students.md"),
    ]:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("|") or "---" in line or "학번" in line:
                        continue
                    cols = [c.strip() for c in line.split("|")]
                    if len(cols) > 8:
                        track = cols[1]
                        student_id = cols[3]
                        eng_name = cols[4]
                        kor_name = cols[8]

                        if student_id.isdigit():
                            id_to_track[student_id] = track
                            id_to_names[student_id] = {"eng": eng_name, "kor": kor_name}

                            clean_eng = re.sub(r"\s+", "", eng_name).lower()
                            if clean_eng:
                                name_to_id[clean_eng] = student_id
                            clean_kor = re.sub(r"\s+", "", kor_name)
                            if clean_kor:
                                name_to_id[clean_kor] = student_id

                            email_addr = cols[5].lower()
                            name_to_id[email_addr] = student_id
    return name_to_id, id_to_track, id_to_names


def get_time_window():
    now = datetime.now(KST)
    days_since_monday = now.weekday()
    deadline = now.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since_monday
    )
    start_time = deadline - timedelta(days=7)
    return start_time, deadline


def extract_gmail_interactive(
    target_week=None, allowed_tracks=None, track_names=None, require_attachment=False
):
    print("Loading student roster...")
    name_to_id, id_to_track, id_to_names = parse_students()

    start_dt, deadline_dt = get_time_window()
    print(
        f"Time Window: {start_dt.strftime('%Y-%m-%d %H:%M')} ~ {deadline_dt.strftime('%Y-%m-%d %H:%M')}"
    )

    # Build regex based on target_week
    week_str = f"0?\\.{target_week}" if target_week else r"0?\.(\d+)"

    strict_re = re.compile(
        rf"(과제|assignment)\s*{week_str}\s*(?:\[|\()?(\d{{10}})(?:\]|\))?",
        re.IGNORECASE,
    )
    any_assignment_re = re.compile(rf"(과제|assignment|{week_str})", re.IGNORECASE)

    new_rows = []

    with sync_playwright() as p:
        user_data_dir = os.path.join(base_dir, ".bin", "playwright_user_data")
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            channel="chrome",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        print("Navigating to mail.google.com...")
        page.goto("https://mail.google.com/")
        print(
            ">>> 브라우저가 화면에 팝업되었습니다. 직접 로그인해주세요! (최대 3분 대기합니다) <<<"
        )

        try:
            page.wait_for_selector('input[name="q"]', timeout=180000)
            print("로그인 확인 완료! 받은편지함 진입 성공.")
        except Exception:
            print("3분 내에 로그인이 확인되지 않거나 Inbox를 렌더링하지 못했습니다.")
            context.close()
            return

        page.wait_for_timeout(2000)

        # Build Gmail query string safely covering the window
        after_str = (start_dt - timedelta(days=1)).strftime("%Y/%m/%d")
        before_str = (deadline_dt + timedelta(days=1)).strftime("%Y/%m/%d")

        if target_week:
            if target_week == "a":
                search_query = (
                    f'("과제 0.a" OR "과제0.a" OR "assignment 0.a" OR "assignment0.a" OR '
                    f'"과제 0.10" OR "과제0.10" OR "assignment 0.10" OR "assignment0.10") '
                    f"after:{after_str} before:{before_str} "
                    f"-from:comments-noreply@docs.google.com -from:wonhyukc@stu.ac.kr"
                )
            elif target_week == "b":
                search_query = (
                    f'("과제 0.b" OR "과제0.b" OR "assignment 0.b" OR "assignment0.b" OR '
                    f'"과제 0.11" OR "과제0.11" OR "assignment 0.11" OR "assignment0.11") '
                    f"after:{after_str} before:{before_str} "
                    f"-from:comments-noreply@docs.google.com -from:wonhyukc@stu.ac.kr"
                )
            else:
                search_query = (
                    f'("과제 0.{target_week}" OR "과제0.{target_week}" OR '
                    f'"assignment 0.{target_week}" OR "assignment0.{target_week}") '
                    f"after:{after_str} before:{before_str} "
                    f"-from:comments-noreply@docs.google.com -from:wonhyukc@stu.ac.kr"
                )
        else:
            search_query = (
                f'("과제" OR "assignment") after:{after_str} '
                f"before:{before_str} -from:comments-noreply@docs.google.com "
                f"-from:wonhyukc@stu.ac.kr"
            )

        print(f"다음 쿼리로 메일을 검색합니다: {search_query}")
        page.fill('input[name="q"]', search_query)
        page.keyboard.press("Enter")

        print("검색 결과 대기 중...")
        page.wait_for_timeout(5000)

        rows = page.locator("tr.zA")
        count = rows.count()
        print(f"총 {count}개의 검색된 이메일을 발견했습니다.")

        seen_ids = set()

        for i in range(count):
            row = rows.nth(i)
            try:
                sub_loc = row.locator("span.bog")
                subject = sub_loc.inner_text().strip() if sub_loc.count() > 0 else ""

                sender_loc = row.locator("div.yW span[name]")
                if sender_loc.count() > 0:
                    sender = (
                        sender_loc.first.get_attribute("name")
                        or sender_loc.first.inner_text()
                    )
                else:
                    sender = ""

                date_loc = row.locator("td.xW span")
                date_str = (
                    date_loc.first.get_attribute("title")
                    if date_loc.count() > 0
                    else ""
                )

                if not date_str and date_loc.count() > 0:
                    date_str = date_loc.first.inner_text()
                if not date_str:
                    date_str = "Thu, 9 Apr 2026 12:00:00 +0900"

                # Exclude 'me' or explicit professor email
                sender_lower = sender.lower()
                if "me" == sender_lower or "wonhyukc@stu.ac.kr" in sender_lower:
                    print(f" -> 발신자(본인) 제외: {date_str} ({subject})")
                    continue

                email_dt = None
                try:
                    email_dt = email.utils.parsedate_to_datetime(date_str)
                    if email_dt.tzinfo is None:
                        email_dt = email_dt.replace(tzinfo=timezone.utc).astimezone(KST)
                    else:
                        email_dt = email_dt.astimezone(KST)
                except Exception:
                    pass

                # Strict Deadline check: Exclude any emails after Monday 09:00
                if email_dt and email_dt > deadline_dt:
                    print(f" -> 지각 제외: {date_str} ({subject})")
                    continue

                # Exclude emails before start_dt (Just in case the query fetched older ones)
                if email_dt and email_dt < start_dt:
                    print(f" -> 기간 이전 제외: {date_str} ({subject})")
                    continue

                has_att = (
                    row.locator("img.yE").count() > 0
                    or row.locator('[aria-label="Attachment"]').count() > 0
                    or "Attachment" in row.inner_html()
                )

            except Exception as _e:
                print(f"Row {i} 파싱 에러: {_e}")
                continue

            subject_lower = subject.lower()
            clean_sub = re.sub(r"\s+", "", subject_lower)
            m_strict = strict_re.search(clean_sub)

            # Extra check: if no week target provided, find week from strict_re or assume general
            found_week = target_week
            if not target_week and m_strict:
                found_week = m_strict.group(2) if len(m_strict.groups()) > 1 else None

            est_id = ""
            # If target_week is fixed, group(2) is the ID.
            # If target_week is not fixed, group(1) is the week, group(2) is the ID.
            if target_week:
                est_id = m_strict.group(2) if m_strict else ""
            else:
                est_id = (
                    m_strict.group(2) if m_strict and len(m_strict.groups()) > 1 else ""
                )

            if not est_id:
                clean_name = re.sub(r"\s+", "", sender).lower()
                if clean_name in name_to_id:
                    est_id = name_to_id[clean_name]
                else:
                    m_id = re.search(r"\d{10}", subject)
                    if m_id:
                        est_id = m_id.group(0)

            # Deduplication: Keep only the most recent email per student ID
            if est_id:
                if est_id in seen_ids:
                    print(f" -> 중복 제외 (과거 메일 무시): {est_id} ({sender})")
                    continue
                seen_ids.add(est_id)

            track_num = id_to_track.get(est_id, "")

            # Filter by track if specific tracks are requested
            if allowed_tracks and track_num not in allowed_tracks:
                if est_id:
                    continue

            score = 0
            reason = "수동 확인 요망(양식불일치/타주차)"
            task_type = "기타"

            if not est_id or est_id not in id_to_track:
                score = 0
                reason = "학번 식별 불가"
                task_type = "기타"
            else:
                task_type = f"0.{found_week}" if found_week else "알수없음"
                if any_assignment_re.search(clean_sub):
                    # Check explicitly other week
                    diff_week_match = re.search(r"0?\.([0-57-9])", clean_sub)
                    expected_week_str = (
                        f"0.{target_week}" if target_week else f"0.{found_week}"
                    )
                    is_this_week = (
                        expected_week_str in clean_sub
                    ) or not diff_week_match

                    if is_this_week:
                        base_score = 2.0
                        violations = []

                        # Attachment check
                        if require_attachment:
                            if not has_att:
                                base_score -= 1.0
                                violations.append("첨부없음")
                        else:
                            if has_att:
                                base_score -= 1.0
                                violations.append("첨부있음")

                        # Strict exact title check (no brackets, exactly (과제|assignment)0.X학번)
                        week_val = target_week if target_week else found_week
                        if week_val == "a":
                            regex_str = r"^(과제|assignment)0?\.(a|10)(\d{10})$"
                        elif week_val == "b":
                            regex_str = r"^(과제|assignment)0?\.(b|11)(\d{10})$"
                        elif week_val == "c":
                            # 12주차 정상 제목은 0.c 또는 0.b
                            regex_str = r"^(과제|assignment)0?\.(c|b)(\d{10})$"
                        else:
                            regex_str = rf"^(과제|assignment)0?\.{week_val}(\d{{10}})$"

                        exact_title_re = re.compile(
                            regex_str,
                            re.IGNORECASE,
                        )
                        is_exact_title = bool(exact_title_re.match(clean_sub))

                        # 12주차(c) 특별 감점 규칙 적용
                        if week_val == "c":
                            if is_exact_title:
                                score = round(base_score, 1)
                                if not violations:
                                    reason = "정확한 양식/조건충족(+2)"
                                else:
                                    reason = (
                                        f"조건위반({','.join(violations)}) ({score})"
                                    )
                            elif "0.12" in clean_sub:
                                base_score -= 0.3
                                violations.append("제목오류(0.12)")
                                score = round(base_score, 1)
                                reason = f"조건위반({','.join(violations)}) ({score})"
                            else:
                                base_score -= 0.2
                                violations.append("제목양식오류")
                                score = round(base_score, 1)
                                reason = f"조건위반({','.join(violations)}) ({score})"
                        else:
                            if not is_exact_title:
                                base_score -= 0.2
                                violations.append("제목양식오류")

                            if not violations:
                                score = 2
                                reason = "정확한 양식/조건충족(+2)"
                            else:
                                score = round(base_score, 1)
                                reason = f"조건위반({','.join(violations)}) ({score})"
                    else:
                        score = 0
                        reason = "타주차 과제(수동확인)"
                        task_type = "기타"
                else:
                    score = 0
                    reason = "과제 아님"
                    task_type = "기타"

            row_data = {
                "학번": est_id,
                "추정하는학번": est_id,
                "track": track_num,
                "점수": score,
                "유형": task_type,
                "이유": reason,
                "날짜": date_str,
                "이름": sender,
                "메일제목": subject,
            }
            new_rows.append(row_data)
            print(f" -> 성공적 파싱: {est_id} ({sender}) | 점수: {score} | {reason}")

        context.close()

    if new_rows:
        out_dir = os.path.join(os.path.dirname(__file__), "../output")
        os.makedirs(out_dir, exist_ok=True)

        # Build out_name based on target_week and track_names
        base_name = f"mail0{target_week}" if target_week else "mail_all"
        if track_names:
            tracks_suffix = "_".join(track_names)
            out_name = f"{base_name}_{tracks_suffix}.csv"
        else:
            out_name = f"{base_name}.csv"

        out_path = os.path.join(out_dir, out_name)

        fieldnames = [
            "학번",
            "추정하는학번",
            "track",
            "점수",
            "유형",
            "이유",
            "날짜",
            "이름",
            "메일제목",
        ]
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_rows)
        print(f"\n========= 총 {len(new_rows)}건 파싱 완료. {out_path} 저장 =========")
    else:
        print("\n========= 조건에 맞는 저장할 데이터가 없습니다. =========")


def run_all_grading_interactive():
    print("Loading student roster...")
    name_to_id, id_to_track, id_to_names = parse_students()

    # py 트랙 고정 (468)
    allowed_tracks = ["468"]

    # 사용자 정의 마감 및 과제 설정
    assignments_config = {
        "0.7": {
            "week_name": "0.7",
            "start_time": "2026-04-13 09:00:00",
            "deadline": "2026-04-20 09:00:00",
            "queries": ["과제 0.7", "assignment 0.7"],
            "require_attachment": True,
        },
        "0.a": {
            "week_name": "0.a",
            "start_time": "2026-04-27 09:00:00",
            "deadline": "2026-05-11 09:00:00",
            "queries": [
                "과제 0.9",
                "assignment 0.9",
                "과제 0.a",
                "assignment 0.a",
                "과제 0.10",
                "assignment 0.10",
            ],
            "require_attachment": False,
        },
        "0.b": {
            "week_name": "0.b",
            "start_time": "2026-05-04 09:00:00",
            "deadline": "2026-05-18 09:00:00",
            "queries": ["과제 0.b", "assignment 0.b", "과제 0.11", "assignment 0.11"],
            "require_attachment": False,
        },
        "0.c": {
            "week_name": "0.c",
            "start_time": "2026-05-11 09:00:00",
            "deadline": "2026-05-25 09:00:00",
            "queries": ["과제 0.c", "assignment 0.c", "과제 0.12", "assignment 0.12"],
            "require_attachment": False,
        },
    }

    with sync_playwright() as p:
        user_data_dir = os.path.join(base_dir, ".bin", "playwright_user_data")
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            channel="chrome",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print("Navigating to mail.google.com...")
        page.goto("https://mail.google.com/")
        print(
            ">>> 브라우저가 화면에 팝업되었습니다. 직접 로그인해주세요! (최대 3분 대기) <<<"
        )

        try:
            page.wait_for_selector('input[name="q"]', timeout=180000)
            print("로그인 확인 완료! 받은편지함 진입 성공.")
        except Exception:
            print("3분 내에 로그인이 확인되지 않았습니다.")
            context.close()
            return

        page.wait_for_timeout(2000)

        for task_key, config in assignments_config.items():
            print(
                f"\n==================== 과제 {task_key} 채점 시작 ===================="
            )
            deadline_dt = datetime.strptime(
                config["deadline"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=KST)
            start_dt = datetime.strptime(
                config["start_time"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=KST)

            # Gmail 검색 쿼리 구성
            or_parts = []
            for q in config["queries"]:
                q_no_space = q.replace(" ", "")
                or_parts.append(f'"{q}"')
                or_parts.append(f'"{q_no_space}"')

            after_str = (start_dt - timedelta(days=1)).strftime("%Y/%m/%d")
            before_str = (deadline_dt + timedelta(days=1)).strftime("%Y/%m/%d")

            or_joined = " OR ".join(or_parts)
            query_str = (
                f"({or_joined}) after:{after_str} before:{before_str} "
                "-from:comments-noreply@docs.google.com -from:wonhyukc@stu.ac.kr"
            )

            print(f"Gmail 검색 쿼리: {query_str}")
            page.fill('input[name="q"]', query_str)
            page.keyboard.press("Enter")

            print("검색 결과 대기 중...")
            page.wait_for_timeout(5000)

            rows = page.locator("tr.zA")
            count = rows.count()
            print(f"총 {count}개의 검색된 이메일을 발견했습니다.")

            seen_ids = set()
            new_rows = []

            for i in range(count):
                row = rows.nth(i)
                try:
                    sub_loc = row.locator("span.bog")
                    subject = (
                        sub_loc.inner_text().strip() if sub_loc.count() > 0 else ""
                    )

                    sender_loc = row.locator("div.yW span[name]")
                    if sender_loc.count() > 0:
                        sender = (
                            sender_loc.first.get_attribute("name")
                            or sender_loc.first.inner_text()
                        )
                    else:
                        sender = ""

                    date_loc = row.locator("td.xW span")
                    date_str = (
                        date_loc.first.get_attribute("title")
                        if date_loc.count() > 0
                        else ""
                    )
                    if not date_str and date_loc.count() > 0:
                        date_str = date_loc.first.inner_text()
                    if not date_str:
                        date_str = "Thu, 9 Apr 2026 12:00:00 +0900"

                    sender_lower = sender.lower()
                    if "me" == sender_lower or "wonhyukc@stu.ac.kr" in sender_lower:
                        continue

                    email_dt = None
                    try:
                        email_dt = email.utils.parsedate_to_datetime(date_str)
                        if email_dt.tzinfo is None:
                            email_dt = email_dt.replace(tzinfo=timezone.utc).astimezone(
                                KST
                            )
                        else:
                            email_dt = email_dt.astimezone(KST)
                    except Exception:
                        pass

                    if email_dt and email_dt > deadline_dt:
                        print(f" -> 지각 제외: {date_str} ({subject})")
                        continue
                    if email_dt and email_dt < start_dt:
                        print(f" -> 기간 이전 제외: {date_str} ({subject})")
                        continue

                    has_att = (
                        row.locator("img.yE").count() > 0
                        or row.locator('[aria-label="Attachment"]').count() > 0
                        or "Attachment" in row.inner_html()
                    )
                except Exception as _e:
                    print(f"Row {i} 파싱 에러: {_e}")
                    continue

                subject_lower = subject.lower()
                clean_sub = re.sub(r"\s+", "", subject_lower)

                # 학번 파싱
                est_id = ""
                m_id = re.search(r"\d{8,11}", subject)
                if m_id:
                    est_id = m_id.group(0)
                else:
                    clean_name = re.sub(r"\s+", "", sender).lower()
                    if clean_name in name_to_id:
                        est_id = name_to_id[clean_name]
                    else:
                        sender_email = sender.split("<")[-1].strip(">").lower()
                        if sender_email in name_to_id:
                            est_id = name_to_id[sender_email]

                if not est_id:
                    est_id = "학번없음"

                track_num = id_to_track.get(est_id, "")
                if track_num not in allowed_tracks:
                    continue

                if est_id != "학번없음":
                    if est_id in seen_ids:
                        print(f" -> 중복 제외 (과거 메일 무시): {est_id} ({sender})")
                        continue
                    seen_ids.add(est_id)

                score = 0
                reason = ""
                if est_id == "학번없음":
                    score = 0
                    reason = "학번 식별 불가"
                else:
                    base_score = 2.0
                    violations = []

                    if config["require_attachment"]:
                        if not has_att:
                            base_score -= 1.0
                            violations.append("첨부없음")
                    else:
                        if has_att:
                            base_score -= 1.0
                            violations.append("첨부있음")

                    is_exact_title = False
                    for q in config["queries"]:
                        q_clean = q.replace(" ", "").lower()
                        q_pattern = re.escape(q_clean)
                        if re.match(rf"^{q_pattern}\d{{8,11}}$", clean_sub):
                            is_exact_title = True
                            break

                    if not is_exact_title:
                        base_score -= 0.2
                        violations.append("제목양식오류")

                    if not violations:
                        score = 2.0
                        reason = "정확한 양식/조건충족(+2)"
                    else:
                        score = round(base_score, 1)
                        reason = f"조건위반({','.join(violations)})"

                formatted_date = (
                    f"{email_dt.month}/{email_dt.day} {email_dt.strftime('%H:%M')}"
                    if email_dt
                    else "알수없음"
                )

                row_data = {
                    "no": "",
                    "학번": est_id,
                    "track": track_num,
                    "점수": score,
                    "유형": config["week_name"],
                    "이유": reason,
                    "날짜": formatted_date,
                    "이름": sender[:20],
                    "메일제목": subject[:20],
                }
                new_rows.append(row_data)
                print(f" -> 채점 성공: {est_id} ({sender}) | 점수: {score} | {reason}")

            if new_rows:
                out_dir = "9output"
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, f"grades_output_{task_key}_py.csv")

                fieldnames = [
                    "no",
                    "학번",
                    "track",
                    "점수",
                    "유형",
                    "이유",
                    "날짜",
                    "이름",
                    "메일제목",
                ]
                with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(new_rows)
                print(f"✅ CSV 저장 완료: {out_path}")

                data_to_append = []
                for nr in new_rows:
                    data_to_append.append(
                        [
                            "",
                            nr["학번"],
                            nr["track"],
                            nr["점수"],
                            nr["유형"],
                            nr["이유"],
                            nr["날짜"],
                            nr["이름"],
                            nr["메일제목"],
                        ]
                    )

                print(f"구글 시트에 '{config['week_name']}' 과제 데이터 추가 시도...")
                from modules.sheet_updater import append_grades_to_sheet

                append_grades_to_sheet(data_to_append, course="py")
            else:
                print(f"⚠️ 과제 {task_key}에 대해 저장할 데이터가 없습니다.")
        context.close()


if __name__ == "__main__":
    print("=" * 60)
    print("📧 [Gmail 과제 이메일 추출기] 실행 안내")
    print("=" * 60)
    print("사용법: python bin/extract_emails.py [주차] [트랙1] [트랙2] ...")
    print("")
    print("예시:")
    print("  1. 특정 주차 전체 트랙 : python bin/extract_emails.py 7")
    print("  2. 특정 주차 특정 트랙 : python bin/extract_emails.py 7 py web1")
    print("  3. 최근 7일 전체(자동) : python bin/extract_emails.py")
    print("-" * 60)
    print("※ 인자 없이 실행 시, 가장 최근 월요일 09:00 마감 기준으로")
    print("   지난 7일간의 모든 메일을 수집하고 각 트랙별 폴더로 자동 분리합니다.")
    print("=" * 60 + "\n")

    parser = argparse.ArgumentParser(description="대화형 Gmail 과제 이메일 추출기")
    parser.add_argument("week", nargs="?", default=None, help="주차 번호 (예: 7)")
    parser.add_argument(
        "tracks", nargs="*", default=[], help="허용할 트랙 목록 (예: py web1 web2)"
    )
    parser.add_argument(
        "--require-attachment",
        action="store_true",
        help="첨부 파일이 있어야 정상으로 간주",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="py 과정의 0.7 ~ 0.c 과제를 일괄적으로 대화형 스크래핑 및 채점 진행",
    )
    args = parser.parse_args()

    track_map = {"py": "468", "web1": "761", "web2": "762"}
    allowed_tracks = [track_map[t] for t in args.tracks if t in track_map]

    if args.run_all:
        run_all_grading_interactive()
    else:
        extract_gmail_interactive(
            target_week=args.week,
            allowed_tracks=allowed_tracks,
            track_names=args.tracks,
            require_attachment=args.require_attachment,
        )
