import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import get_sheet_service

SPREADSHEET_ID = "1lUdHWhyNDTZl9n7s48jn3FCrH6gcbQvGt1nkLBbIM9o"
TARGET_GID = 102396122
SOURCE_GID = 1889091726


def get_sheet_title(service, gid):
    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get("sheets", "")
    for s in sheets:
        props = s.get("properties", {})
        if props.get("sheetId") == int(gid):
            return props.get("title")
    return None


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    service = get_sheet_service(base_dir)

    target_title = get_sheet_title(service, TARGET_GID)
    source_title = get_sheet_title(service, SOURCE_GID)

    print(f"Target Sheet Title: {target_title}")
    print(f"Source Sheet Title: {source_title}")

    if target_title:
        res = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=f"{target_title}!A1:M10")
            .execute()
        )
        print(f"\n--- Target Head ---")
        for row in res.get("values", []):
            print(row)

    if source_title:
        res = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SPREADSHEET_ID, range=f"{source_title}!A1:M10")
            .execute()
        )
        print(f"\n--- Source Head ---")
        for row in res.get("values", []):
            print(row)


if __name__ == "__main__":
    main()
