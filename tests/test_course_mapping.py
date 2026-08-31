import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.peer_grader import build_track_map


def test_build_track_map_returns_dict():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    track_map = build_track_map(base_dir)
    assert isinstance(track_map, dict)

    if len(track_map) > 0:
        # Check if known files produced mapping
        first_key = list(track_map.keys())[0]
        assert track_map[first_key] in [
            "py",
            "wb",
            "468",
            "761",
            "762",
            "14712",
            "15143",
            "15144",
            "04",
            "01",
            "02",
        ]
