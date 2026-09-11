import os
import csv

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_SA_CANDIDATES = [
    "secret.json",
    os.path.expanduser("~/nvme_data/prj/exchange/service-account.json"),
]
SERVICE_ACCOUNT_FILE = next(
    (p for p in _SA_CANDIDATES if os.path.exists(p)), "secret.json"
)
USER_EMAIL = "wonhyukc@stu.ac.kr"


def main():
    try:
        # Load service account credentials with Domain-Wide Delegation for the user
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        creds = creds.with_subject(USER_EMAIL)

        # Build the Gmail service
        service = build("gmail", "v1", credentials=creds)

        # Target timestamp: Wed, 1 Apr 2026 17:29:39 +0900 -> 1775032179
        target_timestamp = 1775032179

        # Query for '과제' or 'assignment' after the specific timestamp
        query = f"subject:(과제 OR assignment) after:{target_timestamp}"

        print(f"Fetching emails for {USER_EMAIL} with query: {query}")

        # Get messages matching query
        results = service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])

        # Handle pagination if there are many emails
        while "nextPageToken" in results:
            page_token = results["nextPageToken"]
            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, pageToken=page_token)
                .execute()
            )
            messages.extend(results.get("messages", []))

        print(f"Found {len(messages)} matching email(s). Extracting details...")

        extracted_data = []
        for msg in messages:
            # Fetch message metadata (Subject, From, Date)
            msg_data = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["Date", "From", "Subject"],
                )
                .execute()
            )

            headers = msg_data["payload"]["headers"]

            date = ""
            sender = ""
            title = ""

            for header in headers:
                if header["name"].lower() == "date":
                    date = header["value"]
                elif header["name"].lower() == "from":
                    sender = header["value"]
                elif header["name"].lower() == "subject":
                    title = header["value"]

            extracted_data.append({"Date": date, "Sender": sender, "Title": title})

        # Save to output/new.csv
        os.makedirs("output", exist_ok=True)
        csv_path = "output/new.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Date", "Sender", "Title"])
            writer.writeheader()
            for row in extracted_data:
                writer.writerow(row)

        print(
            f"Successfully processed and saved {len(extracted_data)} emails to {csv_path}"
        )

    except Exception as e:
        print(f"Error occurred: {e}")


if __name__ == "__main__":
    main()
