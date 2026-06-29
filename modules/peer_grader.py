from collections import Counter


def calculate_majority_vote(evals_list):
    """
    evals_list: list of tuples (evaluator_id, scores_array)
    Returns: majority_scores_array (tuple), has_majority (bool), target_submission_score (float)
    """
    if not evals_list:
        return (), False, 0.0

    score_tuples = [tuple(scores) for _, scores in evals_list]
    counter = Counter(score_tuples)
    majority_scores, majority_count = counter.most_common(1)[0]

    has_majority = majority_count > (len(evals_list) // 2)

    if not has_majority:
        # Tie breaker: highest sum
        majority_scores = sorted(counter.keys(), key=lambda s: sum(s), reverse=True)[0]

    target_submission_score = sum(majority_scores)
    return majority_scores, has_majority, float(target_submission_score)


def calculate_evaluator_points(evals_list, majority_scores, assigned_counts_dict):
    """
    assigned_counts_dict: dict {evaluator_id: actually_assigned_count}
    Returns: dict {evaluator_id: points_earned}
    """
    points = {}
    for evaluator, scores in evals_list:
        if tuple(scores) == majority_scores:
            assigned = assigned_counts_dict.get(evaluator, 1)
            # Default point weight if you get it right is 3.0 / configured_assignments
            points[evaluator] = 3.0 / assigned
        else:
            points[evaluator] = 0.0
    return points


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
                    track_map[row_dict["학번"]] = row_dict.get("강좌번호", track_name)

    parse_md(os.path.join(base_dir, "5input", "students", "py-students.md"), "py")
    parse_md(os.path.join(base_dir, "5input", "students", "wb-students.md"), "wb")

    return track_map
