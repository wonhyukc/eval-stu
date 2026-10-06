import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sheet_updater import get_sheet_service
from update_ids import get_sheet_title, SPREADSHEET_ID, SOURCE_GID


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    service = get_sheet_service(base_dir)
    source_title = get_sheet_title(service, SOURCE_GID)
    source_res = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"{source_title}!A2:H")
        .execute()
    )
    source_rows = source_res.get("values", [])

    with open("/tmp/source_names.txt", "w") as f:
        for row in source_rows:
            f.write(" | ".join(row) + "\n")


if __name__ == "__main__":
    main()
