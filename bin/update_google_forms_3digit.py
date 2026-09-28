#!/usr/bin/env python3
"""
Update Google Forms questions and descriptions to use 3-digit student IDs only.
- Peer Eval Form (1urKd98HpWk-GUuMW3VKtx0egfFZKBcMXbBWRDT7dtpc):
  - Question 2: Evaluator ID -> Last 3 digits
  - Question 3: Reviewee ID -> Last 3 digits
- Assignment Submission Form (1i_tC9larPF-77HyeNyYx68gnHEgzRFusp_aaWVVTQm8):
  - Question 2: Student ID -> Last 3 digits
"""

import os
import sys
import json
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/forms.body"]

PEER_EVAL_FORM_ID = "1urKd98HpWk-GUuMW3VKtx0egfFZKBcMXbBWRDT7dtpc"
ASSIGNMENT_FORM_ID = "1i_tC9larPF-77HyeNyYx68gnHEgzRFusp_aaWVVTQm8"


def get_forms_service():
    candidates = [
        BASE_DIR / "secret.json",
        Path.home() / "nvme_data/prj/exchange/service-account.json",
    ]
    secret_path = next((p for p in candidates if p.exists()), None)
    if secret_path:
        creds = Credentials.from_service_account_file(str(secret_path), scopes=SCOPES)
        return build("forms", "v1", credentials=creds, cache_discovery=False)

    res = subprocess.run(
        ["secret-tool", "lookup", "Title", "drive-api"],
        capture_output=True,
        text=True,
    )
    if res.stdout.strip():
        data = json.loads(res.stdout.strip())
        creds = Credentials.from_service_account_info(data, scopes=SCOPES)
        return build("forms", "v1", credentials=creds, cache_discovery=False)

    raise RuntimeError("No Google service credentials available")


def update_peer_eval_form(service):
    print(f"\n🔄 Updating Peer Eval Form ({PEER_EVAL_FORM_ID})...")
    form = service.forms().get(formId=PEER_EVAL_FORM_ID).execute()
    items = form.get("items", [])

    requests = []
    for idx, item in enumerate(items):
        title = item.get("title", "")

        # Question 2: Evaluator ID
        if "본인의 학번" in title or "Evaluator" in title:
            new_title = "2. 본인의 학번 (뒷 3자리) / 2. Your Student ID (Last 3 Digits)"
            new_desc = "학번 끝 3자리 숫자만 입력하세요. Enter only the last 3 digits of your student ID. (e.g. 740, 895, 857)"
            item_copy = dict(item)
            item_copy["title"] = new_title
            item_copy["description"] = new_desc
            requests.append(
                {
                    "updateItem": {
                        "item": item_copy,
                        "location": {"index": idx},
                        "updateMask": "title,description",
                    }
                }
            )
            print(f"  Target found at index {idx}: {title} -> {new_title}")

        # Question 3: Reviewee ID
        elif "과제 제출자의 학번" in title or "Assignment Submitter" in title:
            new_title = (
                "3. 피평가자 학번 (뒷 3자리) / 3. Reviewee Student ID (Last 3 Digits)"
            )
            new_desc = "배정표에 적힌 피평가자의 끝 3자리 숫자만 입력하세요. Enter only the last 3 digits of the reviewee. (e.g. 741, 904)"
            item_copy = dict(item)
            item_copy["title"] = new_title
            item_copy["description"] = new_desc
            requests.append(
                {
                    "updateItem": {
                        "item": item_copy,
                        "location": {"index": idx},
                        "updateMask": "title,description",
                    }
                }
            )
            print(f"  Target found at index {idx}: {title} -> {new_title}")

    if requests:
        body = {"requests": requests}
        service.forms().batchUpdate(formId=PEER_EVAL_FORM_ID, body=body).execute()
        print("✅ Peer Eval Form successfully updated!")
    else:
        print("⚠️ No matching questions found in Peer Eval Form.")


def update_assignment_form(service):
    print(f"\n🔄 Updating Assignment Form ({ASSIGNMENT_FORM_ID})...")
    form = service.forms().get(formId=ASSIGNMENT_FORM_ID).execute()
    items = form.get("items", [])

    requests = []
    for idx, item in enumerate(items):
        title = item.get("title", "")

        # Question 2: Student ID
        if "학번" in title or "Student ID" in title:
            new_title = "2. 학번 번호 (뒷 3자리) / 2. Student ID (Last 3 digits)"
            new_desc = "학번 끝 3자리 숫자만 입력하세요. Enter only the last 3 digits of your student ID. (e.g. 740, 895, 857)"
            item_copy = dict(item)
            item_copy["title"] = new_title
            item_copy["description"] = new_desc
            requests.append(
                {
                    "updateItem": {
                        "item": item_copy,
                        "location": {"index": idx},
                        "updateMask": "title,description",
                    }
                }
            )
            print(f"  Target found at index {idx}: {title} -> {new_title}")

    if requests:
        body = {"requests": requests}
        service.forms().batchUpdate(formId=ASSIGNMENT_FORM_ID, body=body).execute()
        print("✅ Assignment Form successfully updated!")
    else:
        print("⚠️ No matching questions found in Assignment Form.")


def main():
    service = get_forms_service()
    update_peer_eval_form(service)
    update_assignment_form(service)
    print("\n🎉 Both Google Forms updated to 3-digit student IDs successfully!")


if __name__ == "__main__":
    main()
