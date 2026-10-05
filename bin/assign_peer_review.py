#!/usr/bin/env python3
"""
상호평가 배정 자동화 CLI

3단계 자동 처리:
  ① 구글 폼 원본 → peer-eval-submissions 탭 동기화 (1인 1건 중복 제거)
  ② 균형 무작위 상호평가 배정표 생성 + 마크다운 저장
  ③ peer-eval 탭에 HYPERLINK(URL, 학번3자리) 업로드

사용법:
  ./bin/assign_peer_review.py --course web2 --week 5
  ./bin/assign_peer_review.py --course web1 --week 5 --reviews 2 --exclude-non-submitters
  ./bin/assign_peer_review.py --course py --week 5 --dry-run
"""

import argparse
import os
import random
import subprocess
import sys
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.match_assigner import parse_markdown_table
from modules.sheet_updater import get_sheet_service

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 분반별 설정 ──
COURSE_CONFIG: Dict[str, Dict[str, Any]] = {
    "py": {
        "sheet_id": "1Ni4ZaeIJJdNNvysx5-LFpOF6sh4Emp-cK92DnTUsAyQ",
        "submissions_tab": "상호평가 제출자 답",
        "peer_eval_tab": "상호평가",
        "roster_file": "5input/students/py-students.md",
        "track_id": "14712",
        "course_label": "GPU0940-04 Computing Thinking & Coding (K-Track)",
        "section": "04",
        "language": "ko",
    },
    "web1": {
        "sheet_id": "1pVbDITgW07ErTS4sQHDt1edVDCVKXrLAeRG3fF7-fAk",
        "submissions_tab": "peer-eval-submissions",
        "peer_eval_tab": "peer-eval",
        "roster_file": "5input/students/wb-students.md",
        "track_id": "15143",
        "course_label": "ICE0001-01 Web Programming (Track 15143 / Section 01)",
        "section": "01",
        "language": "en",
    },
    "web2": {
        "sheet_id": "1OMeWuYt45TZMygmkh5hOhqSCCUFYJv4iE0hTY554iAo",
        "submissions_tab": "peer-eval-submissions",
        "peer_eval_tab": "peer-eval",
        "roster_file": "5input/students/wb-students.md",
        "track_id": "15144",
        "course_label": "ICE0001-02 Web Programming (Track 15144 / Section 02)",
        "section": "02",
        "language": "en",
    },
}


# ──────────────────────────────────────────────
# Step 1: 제출 동기화
# ──────────────────────────────────────────────
def sync_submissions(course: str, week: str) -> None:
    """bin/sync_lab_submissions.py 를 호출하여 제출 데이터를 동기화합니다."""
    cmd = [
        sys.executable,
        os.path.join(BASE_DIR, "bin", "sync_lab_submissions.py"),
        "--course",
        course,
        "--week",
        week,
        "--sync",
    ]
    print(f"\n{'='*60}")
    print(f"[Step 1] 제출 데이터 동기화: {course} Week {week}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"❌ 동기화 실패 (exit code: {result.returncode})")
        sys.exit(1)


# ──────────────────────────────────────────────
# Step 2: 제출자·미제출자 분류 및 배정
# ──────────────────────────────────────────────
def load_roster(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """학생 명단을 로드하여 {학번뒷3자리: student_dict} 맵을 반환합니다."""
    roster_path = os.path.join(BASE_DIR, cfg["roster_file"])
    if not os.path.exists(roster_path):
        print(f"❌ 명단 파일 없음: {roster_path}")
        sys.exit(1)
    all_students = parse_markdown_table(roster_path)
    target = [
        s for s in all_students if str(s.get("강좌번호", "")).strip() == cfg["track_id"]
    ]
    return {str(s["학번"]).strip()[-3:]: s for s in target}


def load_submitted(
    service: Any, cfg: Dict[str, Any], roster_last3: Set[str]
) -> Dict[str, str]:
    """peer-eval-submissions 탭에서 제출자 {학번뒷3자리: url} 매핑을 반환합니다."""
    tab = cfg["submissions_tab"]
    res = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=cfg["sheet_id"], range=f"'{tab}'!A:I")
        .execute()
    )
    rows = res.get("values", [])
    submitted: Dict[str, str] = {}
    for r in rows[1:]:
        if len(r) < 4:
            continue
        last3 = str(r[2]).strip().lstrip("'")
        url = str(r[3]).strip()
        if last3 in roster_last3 and url:
            submitted[last3] = url
    return submitted


def assign_reviews(
    submitted_last3: List[str],
    reviews_per_person: int,
    seed: int = 42,
) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
    """균형 무작위 상호평가 배정을 수행합니다.

    Returns:
        assignments: {evaluator_last3: [reviewee_last3, ...]}
        receive_counts: {student_last3: 피평가 횟수}
    """
    random.seed(seed)
    n = len(submitted_last3)
    if n < reviews_per_person + 1:
        print(f"❌ 제출자가 {n}명으로 1인당 {reviews_per_person}명 배정이 불가합니다.")
        sys.exit(1)

    shuffled = list(submitted_last3)
    random.shuffle(shuffled)

    assignments: Dict[str, List[str]] = {}
    receive_counts = {s: 0 for s in submitted_last3}

    for evaluator in shuffled:
        candidates = [s for s in shuffled if s != evaluator]
        random.shuffle(candidates)
        candidates.sort(key=lambda x: receive_counts[x])
        chosen = candidates[:reviews_per_person]
        assignments[evaluator] = chosen
        for c in chosen:
            receive_counts[c] += 1

    return assignments, receive_counts


# ──────────────────────────────────────────────
# Step 3-a: 마크다운 저장
# ──────────────────────────────────────────────
def generate_markdown(
    cfg: Dict[str, Any],
    week: str,
    roster_last3_map: Dict[str, Dict[str, Any]],
    submitted: Dict[str, str],
    assignments: Dict[str, List[str]],
    receive_counts: Dict[str, int],
    non_submitted: List[str],
    reviews_per_person: int,
    exclude_non_submitters: bool,
) -> str:
    """배정 결과를 마크다운 문자열로 생성합니다."""
    total = len(roster_last3_map)
    n_sub = len(submitted)
    n_non = len(non_submitted)
    track = cfg["track_id"]
    label = cfg["course_label"]

    # 영어/한국어 분기
    is_en = cfg["language"] == "en"

    lines: List[str] = []
    lines.append(
        f"# Week {week} Peer Review Assignments"
        f" (Track {track} / {label.split('(')[0].strip()})\n"
        if is_en
        else f"# {week}주차 상호평가 배정표 (트랙 {track})\n"
    )

    lines.append(f"- **Course**: {label}")
    lines.append(
        f"- **Total Roster**: {total} students"
        if is_en
        else f"- **전체 수강생**: {total}명"
    )
    lines.append(
        f"- **Submitters (Evaluators & Reviewees)**: {n_sub} students"
        if is_en
        else f"- **제출자 (평가자 겸 피평가자)**: {n_sub}명"
    )

    if exclude_non_submitters:
        lines.append(
            f"- **Non-submitters (Excluded)**: {n_non} students"
            if is_en
            else f"- **미제출자 (채점 기회 박탈)**: {n_non}명"
        )
        policy = (
            "Non-submitters are excluded from both evaluating and being "
            f"evaluated (forfeited). Each submitter reviews {reviews_per_person} peers."
            if is_en
            else f"미제출자는 평가자·피평가자 모두에서 제외됩니다. "
            f"제출자는 각각 {reviews_per_person}명을 평가합니다."
        )
    else:
        lines.append(
            f"- **Non-submitters**: {n_non} students (evaluate only)"
            if is_en
            else f"- **미제출자**: {n_non}명 (평가만 수행)"
        )
        policy = (
            f"Each student reviews {reviews_per_person} peers. "
            "Non-submitters evaluate but cannot be evaluated."
            if is_en
            else f"전체 학생이 {reviews_per_person}명을 평가하되, "
            "미제출자는 피평가 대상에서 제외됩니다."
        )
    lines.append(f"- **Policy**: {policy}")
    lines.append("")

    # 배정표 테이블
    hdr_title = (
        "## 1. Peer Review Assignment Table\n" if is_en else "## 1. 상호평가 배정표\n"
    )
    lines.append(hdr_title)

    # 동적 열 생성
    reviewee_hdrs = " | ".join(
        [
            f"Reviewee {i+1}" if is_en else f"피평가자 {i+1}"
            for i in range(reviews_per_person)
        ]
    )
    lines.append(f"| No | Evaluator ID | Status | {reviewee_hdrs} |")
    sep = " | ".join([":---"] * reviews_per_person)
    lines.append(f"| :---: | :---: | :---: | {sep} |")

    no = 1
    for last3 in sorted(assignments.keys()):
        reviewees = assignments[last3]
        cells = []
        for r3 in reviewees:
            url = submitted.get(r3, "")
            cells.append(f"[{r3}]({url})" if url else r3)
        cells_str = " | ".join(cells)
        status = "Submitted" if last3 in submitted else "Not Submitted"
        lines.append(f"| {no} | **{last3}** | {status} | {cells_str} |")
        no += 1

    lines.append("")

    # 피평가 횟수
    lines.append(
        "## 2. Reviewees Received Reviews Count\n"
        if is_en
        else "## 2. 피평가자별 수신 횟수\n"
    )
    lines.append("| No | Student ID (Last 3 Digits) | Received Reviews Count |")
    lines.append("| :---: | :---: | :---: |")
    no = 1
    for last3 in sorted(receive_counts.keys()):
        cnt = receive_counts[last3]
        lines.append(f"| {no} | **{last3}** | {cnt} reviews |")
        no += 1

    lines.append("")

    # 미제출자
    lines.append(
        "## 3. Non-Submitters (Excluded — Forfeited Evaluation Opportunity)\n"
        if is_en
        else "## 3. 미제출자 (채점 기회 박탈)\n"
    )
    lines.append("| No | Student ID (Last 3 Digits) | Status |")
    lines.append("| :---: | :---: | :--- |")
    no = 1
    for last3 in non_submitted:
        status_txt = "Not Submitted — Excluded" if is_en else "미제출 — 제외"
        lines.append(f"| {no} | **{last3}** | {status_txt} |")
        no += 1
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Step 3-b: 시트 업로드
# ──────────────────────────────────────────────
def upload_peer_eval(
    service: Any,
    cfg: Dict[str, Any],
    assignments: Dict[str, List[str]],
    submitted: Dict[str, str],
    non_submitted: List[str],
    reviews_per_person: int,
    is_en: bool,
) -> None:
    """peer-eval 탭에 HYPERLINK 수식으로 배정표를 업로드합니다."""
    tab = cfg["peer_eval_tab"]
    sheet_id = cfg["sheet_id"]

    # Clear
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range=f"'{tab}'!A1:Z200"
        ).execute()
    except Exception as e:
        print(f"  ⚠️ clear 실패 (무시): {e}")

    # 헤더
    reviewee_hdrs = [
        f"Reviewee {i+1}" if is_en else f"피평가자 {i+1}"
        for i in range(reviews_per_person)
    ]
    sheet_rows: List[List[Any]] = [["No", "Evaluator ID", "Status"] + reviewee_hdrs]

    # 제출자 배정
    no = 1
    for last3 in sorted(assignments.keys()):
        reviewees = assignments[last3]
        r_cells = []
        for r3 in reviewees:
            url = submitted.get(r3, "")
            if url:
                r_cells.append(f'=HYPERLINK("{url}", "{r3}")')
            else:
                r_cells.append(r3)
        sheet_rows.append([no, f"'{last3}", "Submitted"] + r_cells)
        no += 1

    # 미제출자
    sheet_rows.append([])
    status_label = "Excluded" if is_en else "제외"
    sheet_rows.append(["", "Non-Submitters", status_label] + [""] * reviews_per_person)
    no_ns = 1
    for last3 in non_submitted:
        status_txt = "Not Submitted — Excluded" if is_en else "미제출 — 제외"
        sheet_rows.append([no_ns, f"'{last3}", status_txt] + [""] * reviews_per_person)
        no_ns += 1

    cols = chr(ord("A") + 2 + reviews_per_person)
    update_range = f"'{tab}'!A1:{cols}{len(sheet_rows)}"
    update_res = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=sheet_id,
            range=update_range,
            valueInputOption="USER_ENTERED",
            body={"values": sheet_rows},
        )
        .execute()
    )
    print(
        f"  ✅ '{tab}' 탭 업로드: "
        f"{update_res.get('updatedCells')}셀 ({len(sheet_rows)}행)"
    )


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="상호평가 배정 자동화 (동기화 → 배정 → 시트 업로드)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  %(prog)s --course web2 --week 5\n"
            "  %(prog)s --course web1 --week 5 --reviews 3\n"
            "  %(prog)s --course py --week 5 --dry-run\n"
        ),
    )
    parser.add_argument(
        "--course",
        required=True,
        choices=["py", "web1", "web2"],
        help="과목 분반",
    )
    parser.add_argument("--week", required=True, help="주차 번호")
    parser.add_argument(
        "--reviews",
        type=int,
        default=2,
        help="1인당 평가 수 (기본: 2)",
    )
    parser.add_argument(
        "--exclude-non-submitters",
        action="store_true",
        default=True,
        help="미제출자를 평가자에서도 완전 제외 (기본: True)",
    )
    parser.add_argument(
        "--include-non-submitters",
        action="store_true",
        help="미제출자도 평가자로 참여 (기존 정책)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="무작위 시드 (기본: 42, 재현 가능)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="시트 반영 없이 미리보기만",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Step 1 동기화를 건너뛰고 기존 시트 데이터 사용",
    )
    args = parser.parse_args()

    exclude = not args.include_non_submitters
    cfg = COURSE_CONFIG[args.course]
    is_en = cfg["language"] == "en"

    print(f"🚀 상호평가 배정 자동화: {args.course} Week {args.week}")
    print(f"   1인당 평가 수: {args.reviews}")
    print(f"   미제출자 제외: {'Yes' if exclude else 'No'}")
    print(f"   Dry-run: {'Yes' if args.dry_run else 'No'}")

    # ── Step 1: 동기화 ──
    if not args.skip_sync and not args.dry_run:
        sync_submissions(args.course, args.week)
    elif args.skip_sync:
        print("\n⏭️  Step 1 건너뜀 (--skip-sync)")

    # ── Step 2: 제출자 로드 및 배정 ──
    print(f"\n{'='*60}")
    print(f"[Step 2] 배정표 생성")
    print(f"{'='*60}")

    roster_map = load_roster(cfg)
    print(f"  전체 수강생: {len(roster_map)}명")

    if not args.dry_run:
        service = get_sheet_service(BASE_DIR)
        submitted = load_submitted(service, cfg, set(roster_map.keys()))
    else:
        # dry-run: 동기화 없이 직접 폼에서 읽기
        service = get_sheet_service(BASE_DIR)
        submitted = load_submitted(service, cfg, set(roster_map.keys()))

    submitted_last3 = sorted(submitted.keys())
    non_submitted = sorted(set(roster_map.keys()) - set(submitted_last3))

    print(f"  제출자: {len(submitted_last3)}명 → {submitted_last3}")
    print(f"  미제출자: {len(non_submitted)}명 → {non_submitted}")

    if len(submitted_last3) < args.reviews + 1:
        print(f"❌ 제출자({len(submitted_last3)}명)가 너무 적습니다.")
        sys.exit(1)

    # 배정
    if exclude:
        # 미제출자 완전 제외: 제출자만 평가
        evaluator_ids = submitted_last3
    else:
        # 기존 정책: 전체 학생이 평가, 피평가는 제출자만
        evaluator_ids = sorted(roster_map.keys())

    assignments, receive_counts = assign_reviews(
        submitted_last3 if exclude else evaluator_ids,
        args.reviews,
        seed=args.seed,
    )

    rc_vals = list(receive_counts.values())
    print(
        f"\n  배정 완료: {len(assignments)}명 × {args.reviews}명"
        f" | 피평가 min={min(rc_vals)} max={max(rc_vals)}"
    )

    # ── Step 3-a: 마크다운 저장 ──
    print(f"\n{'='*60}")
    print(f"[Step 3] 결과 저장 및 시트 업로드")
    print(f"{'='*60}")

    md_content = generate_markdown(
        cfg,
        args.week,
        roster_map,
        submitted,
        assignments,
        receive_counts,
        non_submitted,
        args.reviews,
        exclude,
    )

    output_path = os.path.join(
        BASE_DIR,
        "9output",
        f"week{args.week}_peer_review_assignments_{cfg['track_id']}.md",
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  ✅ 마크다운 저장: {output_path}")

    # ── Step 3-b: 시트 업로드 ──
    if args.dry_run:
        print("\n  ⏭️  Dry-run 모드: 시트 업로드 건너뜀")
        print("\n📄 미리보기:")
        print(md_content)
    else:
        upload_peer_eval(
            service,
            cfg,
            assignments,
            submitted,
            non_submitted,
            args.reviews,
            is_en,
        )

    print(f"\n🎉 완료! ({args.course} Week {args.week})")


if __name__ == "__main__":
    main()
