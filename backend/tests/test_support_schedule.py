"""Tests for support schedule is_open_now / next_open_at."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from supportchat.schedule import (
    ensure_default_schedule,
    is_open_now,
    next_open_at,
    schedule_public_payload,
)

MSK = ZoneInfo("Europe/Moscow")


@pytest.mark.django_db
def test_default_schedule_seed() -> None:
    schedule = ensure_default_schedule()
    assert schedule.timezone == "Europe/Moscow"
    days = list(schedule.days.order_by("weekday"))
    assert len(days) == 7
    assert days[0].is_closed is False
    assert list(days[0].intervals.values_list("start_time", "end_time"))
    assert days[4].intervals.first().end_time.hour == 17
    assert days[5].is_closed is True
    assert days[6].is_closed is True


@pytest.mark.django_db
def test_is_open_tuesday_morning() -> None:
    ensure_default_schedule()
    # 2026-08-11 is Tuesday
    at = datetime(2026, 8, 11, 10, 0, tzinfo=MSK)
    assert is_open_now(at) is True


@pytest.mark.django_db
def test_is_closed_friday_after_17() -> None:
    ensure_default_schedule()
    # 2026-08-14 Friday
    at = datetime(2026, 8, 14, 17, 30, tzinfo=MSK)
    assert is_open_now(at) is False


@pytest.mark.django_db
def test_is_closed_saturday() -> None:
    ensure_default_schedule()
    at = datetime(2026, 8, 15, 12, 0, tzinfo=MSK)
    assert is_open_now(at) is False
    nxt = next_open_at(at)
    assert nxt is not None
    assert nxt.weekday() == 0  # Monday
    assert nxt.hour == 9


@pytest.mark.django_db
def test_lunch_break_two_intervals() -> None:
    schedule = ensure_default_schedule()
    day = schedule.days.get(weekday=0)
    day.intervals.all().delete()
    from datetime import time

    from supportchat.models import SupportScheduleInterval

    SupportScheduleInterval.objects.create(day=day, start_time=time(9, 0), end_time=time(13, 0))
    SupportScheduleInterval.objects.create(day=day, start_time=time(14, 0), end_time=time(18, 0))
    at_lunch = datetime(2026, 8, 10, 13, 30, tzinfo=MSK)  # Monday
    assert is_open_now(at_lunch) is False
    at_afternoon = datetime(2026, 8, 10, 14, 0, tzinfo=MSK)
    assert is_open_now(at_afternoon) is True


@pytest.mark.django_db
def test_schedule_public_payload() -> None:
    ensure_default_schedule()
    at = datetime(2026, 8, 11, 10, 0, tzinfo=MSK)
    payload = schedule_public_payload(at=at)
    assert payload["is_open_now"] is True
    assert payload["timezone"] == "Europe/Moscow"
    assert len(payload["days"]) == 7
