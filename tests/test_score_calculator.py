import unittest
import csv
import builtins
import sys
import os

# 모듈 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.score_calculator import main


class TestScoreCalculator(unittest.TestCase):
    @unittest.skipIf(
        not os.path.exists("students_all - all_emails.csv"), "Needs real CSV data"
    )
    def test_grading_count(self):
        """
        현재 score_calculator.py를 실행했을 때 5건 이하만 점수를 받는지 검증하고 원인을 파악하기 위한 테스트입니다.
        """
        # 1. 파일 경로 하드코딩 우회 (deadline.csv -> input/deadline.csv)
        original_open = builtins.open

        def mock_open(file, *args, **kwargs):
            if file == "deadline.csv":
                return original_open("input/deadline.csv", *args, **kwargs)
            return original_open(file, *args, **kwargs)

        # apply mock
        self.original_open = original_open
        builtins.open = mock_open

        try:
            # 2. 메인 로직 실행
            main()

            # 3. 채점 결과 확인
            scored_count = 0
            total_emails = 0
            with self.original_open(
                "output/scored_all_emails.csv", "r", encoding="utf-8"
            ) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_emails += 1
                    score = row.get("점수", "").strip()
                    if score and score != "0":
                        scored_count += 1

            print(f"\n전체 메일 수: {total_emails}")
            print(f"점수를 부여받은 메일 수: {scored_count}")

            # 테스트가 실패하더라도 채점된 수가 5보다 큰지 확인하여 문제 재현
            self.assertGreater(
                scored_count,
                5,
                f"채점된 건수가 너무 적습니다. 현재 채점 건수: {scored_count}건",
            )

        finally:
            # restore mock
            builtins.open = self.original_open


if __name__ == "__main__":
    unittest.main()
