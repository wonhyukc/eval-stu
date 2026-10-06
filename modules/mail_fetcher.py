from modules.auth import get_gmail_service


def fetch_assignment_emails(query_string, max_results=100):
    """
    지정된 검색 쿼리(query_string)와 일치하는 이메일 목록 데이터를 수집합니다.
    반환값: dict 리스트 (메시지 ID, 스레드 ID, 제목, 발신자, 날짜, 교수 피드백 여부)
    """
    service = get_gmail_service()

    messages = []
    page_size = min(max_results, 500) if max_results else 500
    request = (
        service.users()
        .messages()
        .list(userId="me", q=query_string, maxResults=page_size)
    )
    while request is not None:
        results = request.execute()
        messages.extend(results.get("messages", []))
        if max_results and len(messages) >= max_results:
            messages = messages[:max_results]
            break
        request = service.users().messages().list_next(request, results)

    email_data = []

    def _has_attachment(payload):
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("filename"):
                    return True
                if _has_attachment(part):
                    return True
        return False

    for msg in messages:
        msg_detail = (
            service.users()
            .messages()
            .get(userId="me", id=msg["id"], format="full")
            .execute()
        )
        headers = msg_detail["payload"]["headers"]

        subject = next(
            (h["value"] for h in headers if h["name"].lower() == "subject"),
            "No Subject",
        )

        # 동일한 메일 스레드가 중복 수집되는 것을 방지하기 위해 회신(Re) 메일은 제외
        subject_lower = subject.strip().lower()
        if subject_lower.startswith("re:") or subject_lower.startswith("re "):
            continue

        sender = next(
            (h["value"] for h in headers if h["name"].lower() == "from"),
            "Unknown Sender",
        )
        date_str = next(
            (h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date"
        )

        thread_id = msg_detail["threadId"]
        has_att = _has_attachment(msg_detail["payload"])

        email_data.append(
            {
                "message_id": msg["id"],
                "thread_id": thread_id,
                "subject": subject,
                "sender": sender,
                "date_str": date_str,
                "has_attachment": has_att,
                "is_replied_by_instructor": check_replied_by_instructor(
                    service, thread_id
                ),
            }
        )

    return email_data


def check_replied_by_instructor(
    service, thread_id, instructor_email="wonhyukc@stu.ac.kr"
):
    """
    메일 쓰레드(Thread)를 조회하여, 교강사가 회신한 피드백 메일이 포함되어 있는지 확인합니다.
    """
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="metadata")
        .execute()
    )
    t_messages = thread.get("messages", [])

    for t_m in t_messages:
        headers = t_m["payload"]["headers"]
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
        if instructor_email.lower() in sender.lower():
            return True

    return False


if __name__ == "__main__":
    print("메일 수집 테스트 (과제 0.4, 최신 5건)...")
    emails = fetch_assignment_emails("0.4", max_results=5)
    for e in emails:
        print(
            f"[{e['date_str']}] {e['sender']}: {e['subject']} (교수회신: {e['is_replied_by_instructor']})"
        )
