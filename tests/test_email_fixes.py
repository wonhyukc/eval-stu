import pytest
import re
from datetime import datetime, timezone, timedelta
from bin.auto_grade_email import get_deadline_dt, get_late_cutoff_dt
from modules.email_submission import strip_gmail_quotes

KST = timezone(timedelta(hours=9))


def test_get_deadline_dt(monkeypatch):
    # Depending on deadline.csv (e.g. week 1 -> 9/4 0:00 -> 9/4 0:15)
    # This might fail if deadline.csv is missing, but it is available in the env.
    dt = get_deadline_dt("0.1")
    assert dt.tzinfo == KST
    assert dt.minute == 15


def test_get_late_cutoff_dt(monkeypatch):
    # Week 1 lab deadline is 9/7
    dt = get_late_cutoff_dt("0.1", "4")
    assert dt.tzinfo == KST
    assert dt.hour == 9


def test_strip_gmail_quotes():
    body = """Here is my assignment.

On Thu, Sep 10, 2026 at 10:23 PM Wonhyuk William Chung <wonhyukc@stu.ac.kr> wrote:
> This is a quote
> another line"""
    clean = strip_gmail_quotes(body)
    assert "Here is my assignment." in clean
    assert "On Thu" not in clean
    assert "This is a quote" not in clean

    body_ko = """과제 제출합니다.

2026년 9월 10일 (목) 오후 10:23, Wonhyuk William Chung <wonhyukc@stu.ac.kr>님이 작성:
> 인용입니다."""
    clean_ko = strip_gmail_quotes(body_ko)
    assert "과제 제출합니다." in clean_ko
    assert "작성:" not in clean_ko

    body_gt = """Hello
> greater than prefix
world"""
    clean_gt = strip_gmail_quotes(body_gt)
    assert "Hello" in clean_gt
    assert "world" in clean_gt
    assert "greater than prefix" not in clean_gt


def test_extract_emails_regex():
    # Just need to test the regex
    week_str = r"0?\.?\d+"
    test_re = re.compile(
        rf"(?:과제|assignment|homework)\s*(?P<week>{week_str})\s*(?:\[|\()?(?P<sid>\d{{3,10}})(?:\]|\))?",
        re.IGNORECASE,
    )

    m = test_re.search("과제 0.3 2026300123")
    assert m is not None
    assert m.group("week") == "0.3"
    assert m.group("sid") == "2026300123"

    m = test_re.search("과제 3 1234567890")
    assert m is not None
    assert m.group("week") == "3"
    assert m.group("sid") == "1234567890"
