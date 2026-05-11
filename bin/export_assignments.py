#!/usr/bin/env python3
import os
import sys
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1F69Wtmrr3MYMJI8jgjPKBWh3m8tDaX6QyBVDSHH4vEc"
TARGET_GID = 794156024

def get_sheet_service():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    secret_path = os.path.join(base_dir, "secret.json")
    if os.path.exists(secret_path):
        creds = Credentials.from_service_account_file(secret_path, scopes=SCOPES)
    else:
        import google.auth
        creds, _ = google.auth.default(scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def get_target_sheet_title(service):
    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get("sheets", "")
    for s in sheets:
        props = s.get("properties", {})
        if props.get("sheetId") == TARGET_GID:
            return props.get("title")
    return None

def parse_markdown(md_file, track_name):
    rows = []
    if not os.path.exists(md_file):
        return rows
    with open(md_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    in_table = False
    for line in lines:
        line = line.strip()
        if line.startswith("| Evaluator"):
            in_table = True
            continue
        if in_table and line.startswith("| :---"):
            continue
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            clean_parts = [track_name]
            for p in parts:
                p = p.replace("**", "")
                if "[" in p and "](" in p:
                    text = p.split("]")[0].replace("[", "")
                    url = p.split("](")[1].replace(")", "")
                    clean_parts.append(f'=HYPERLINK("{url}", "{text}")')
                else:
                    clean_parts.append(p)
            rows.append(clean_parts)
    return rows

def main():
    service = get_sheet_service()
    sheet_title = get_target_sheet_title(service)
    if not sheet_title:
        print("Sheet not found")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    md1 = os.path.join(base_dir, "9output", "week10_peer_review_assignments_761.md")
    md2 = os.path.join(base_dir, "9output", "week10_peer_review_assignments_762.md")

    rows_761 = parse_markdown(md1, "761")
    rows_762 = parse_markdown(md2, "762")

    all_rows = []
    # Add Header
    all_rows.append(["Track", "Evaluator / 평가자 (학번)", "Reviewee 1 / 피평가자 1", "Reviewee 2 / 피평가자 2", "Reviewee 3 / 피평가자 3"])
    all_rows.extend(rows_761)
    all_rows.extend(rows_762)

    range_name = f"{sheet_title}!A:E"
    service.spreadsheets().values().clear(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()

    body = {"values": all_rows}
    result = service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    print(f"✅ Updated {result.get('updatedCells')} cells in {sheet_title}")

if __name__ == "__main__":
    main()
