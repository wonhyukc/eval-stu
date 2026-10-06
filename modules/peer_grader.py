from collections import Counter
import re
from pathlib import Path

from modules.sheet_updater import normalize_track


def normalize_student_id(raw):
    """폼·명부의 숫자 학번을 끝 3자리로 통일하고 앞쪽 0을 보존한다."""
    value = str(raw or "").strip().lstrip("'").strip()
    if not re.fullmatch(r"[0-9]{1,10}", value):
        return ""
    return value[-3:].zfill(3)


def deduplicate_and_filter_evals(raw_evals, assignments):
    """
    raw_evals: list of dicts with 'evaluator', 'target', 'scores' (in order of submission)
    assignments: dict {evaluator_id: [target_id, ...]}
    Returns: dict {(evaluator, target): scores_array} keeping only the latest valid submission.
    """
    submitted_evaluations = {}
    for ev in raw_evals:
        evaluator = ev["evaluator"]
        target = ev["target"]
        scores = ev["scores"]

        # Filter self-evaluations and not-assigned
        if evaluator == target:
            continue
        if not evaluator or target not in assignments.get(evaluator, []):
            continue

        # Deduplicate (latest overwrites earlier)
        submitted_evaluations[(evaluator, target)] = scores

    return submitted_evaluations


def calculate_majority_vote(evals_list):
    """
    evals_list: list of tuples (evaluator_id, scores_array)
    Returns: majority_scores_array (tuple), has_majority (bool), target_submission_score (float)
    """
    if not evals_list:
        return (), False, 0.0

    question_count = len(evals_list[0][1])
    if any(len(scores) != question_count for _, scores in evals_list):
        raise ValueError("상호평가 문항 수가 서로 다릅니다.")
    majority_scores = []
    has_majority = True
    for i in range(question_count):
        counter = Counter(scores[i] for _, scores in evals_list)
        # 문항별 최빈값을 선택한다. 동수이면 기존 관용 정책대로 높은 점수 우선.
        score, count = max(counter.items(), key=lambda item: (item[1], item[0]))
        majority_scores.append(score)
        has_majority = has_majority and count > len(evals_list) // 2
    return tuple(majority_scores), has_majority, float(sum(majority_scores))


def calculate_evaluator_points(evals_list, majority_scores, assigned_counts_dict):
    """
    assigned_counts_dict: dict {evaluator_id: actually_assigned_count}
    Returns: dict {evaluator_id: points_earned}
    """
    points = {}
    for evaluator, scores in evals_list:
        if len(scores) != len(majority_scores) or not majority_scores:
            raise ValueError("상호평가 문항 수가 올바르지 않습니다.")
        assigned = assigned_counts_dict.get(evaluator, 0)
        if assigned <= 0:
            raise ValueError("평가자의 실제 배정 건수를 확인할 수 없습니다.")
        matches = sum(
            score == majority for score, majority in zip(scores, majority_scores)
        )
        earned = (3.0 / assigned) * (matches / len(majority_scores))
        points[evaluator] = points.get(evaluator, 0.0) + earned
    return points


def load_review_assignments(paths):
    """생성된 신·구 마크다운 배정표에서 평가자별 실제 피평가자를 읽는다."""
    assignments = {}
    for path in paths:
        evaluator_idx = -1
        target_idxs = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().split("|")[1:-1]]
            if any("Evaluator" in c or "평가자" in c for c in cells):
                evaluator_idx = next(
                    (
                        i
                        for i, c in enumerate(cells)
                        if "Evaluator" in c or ("평가자" in c and "피평가자" not in c)
                    ),
                    -1,
                )
                target_idxs = [
                    i for i, c in enumerate(cells) if "Reviewee" in c or "피평가자" in c
                ]
                continue
            if evaluator_idx < 0 or not target_idxs or len(cells) <= max(target_idxs):
                continue

            def cell_id(cell):
                link = re.fullmatch(r"\[([0-9]+)\]\(.*\)", cell)
                return normalize_student_id(
                    link.group(1) if link else cell.strip("*` ")
                )

            evaluator = cell_id(cells[evaluator_idx])
            if not evaluator:
                continue
            targets = [cell_id(cells[i]) for i in target_idxs]
            targets = [t for t in targets if t]
            if (
                evaluator in assignments
                or evaluator in targets
                or len(set(targets)) != len(targets)
            ):
                raise ValueError("배정표에 중복 배정 또는 자기 평가가 있습니다.")
            assignments[evaluator] = targets
    if not assignments:
        raise ValueError("배정표에서 평가자·피평가자 항목을 찾지 못했습니다.")
    return assignments


def find_review_assignment_paths(base_dir, course, week):
    """해당 분반·주차의 자동 생성 배정표를 찾는다. 최신 강좌번호를 우선한다."""
    tracks = {
        "py": [("14712", "468")],
        "web1": [("15143", "761")],
        "web2": [("15144", "762")],
        "web": [("15143", "761"), ("15144", "762")],
    }
    if course not in tracks:
        raise ValueError("배정표 조회는 py/web1/web2/web 과정을 지원합니다.")
    paths = []
    for aliases in tracks[course]:
        candidates = [
            Path(base_dir) / "9output" / f"week{w}_peer_review_assignments_{track}.md"
            for track in aliases
            for w in dict.fromkeys((str(week), str(int(week))))
        ]
        chosen = next((p for p in candidates if p.exists()), None)
        if chosen is None:
            raise ValueError(
                "해당 주차의 배정표가 없습니다. --assignments로 배정표 경로를 지정하세요."
            )
        paths.append(chosen)
    return paths


def normalize_final_scores(target_pts, evaluator_earned_pts, total_max_sub_score):
    """
    target_pts: float (sum of majority scores)
    evaluator_earned_pts: float (sum of earned eval points)
    total_max_sub_score: float (max sub score)
    Returns: sub_ratio, eval_ratio, total_ratio
    """
    if total_max_sub_score == 0:
        total_max_sub_score = 1.0

    sub_ratio = (target_pts / total_max_sub_score) * 0.8
    eval_ratio = (min(evaluator_earned_pts, 3.0) / 3.0) * 0.2

    return sub_ratio, eval_ratio, sub_ratio + eval_ratio


def build_track_map(base_dir):
    import os

    track_map = {}

    def parse_md(filepath, track_name):
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        headers = []
        for line in lines:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if not headers and "학번" in line:
                headers = cols
                continue
            if len(cols) == 0 or "---" in line:
                continue
            if headers and len(cols) >= len(headers):
                row_dict = dict(zip(headers, cols))
                if "학번" in row_dict and row_dict["학번"]:
                    sid = normalize_student_id(row_dict["학번"])
                    if sid:
                        track_map[sid] = normalize_track(
                            row_dict.get("강좌번호") or track_name
                        )

    parse_md(os.path.join(base_dir, "5input", "students", "py-students.md"), "4")
    parse_md(os.path.join(base_dir, "5input", "students", "wb-students.md"), "wb")

    return track_map
