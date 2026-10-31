from datetime import UTC, datetime, timedelta, timezone

import pytest

from apps.bookings.rules import intervals_overlap, is_available, validate_interval


def utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 30, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ((utc(10), utc(11)), (utc(10), utc(11)), True),  # iguais
        ((utc(10), utc(12)), (utc(11), utc(13)), True),  # parcial
        ((utc(11), utc(13)), (utc(10), utc(12)), True),  # parcial inverso
        ((utc(10), utc(14)), (utc(11), utc(12)), True),  # contido
        ((utc(11), utc(12)), (utc(10), utc(14)), True),  # contém
        ((utc(10), utc(11)), (utc(11), utc(12)), False),  # consecutivos
        ((utc(11), utc(12)), (utc(10), utc(11)), False),
        ((utc(10), utc(11)), (utc(12), utc(13)), False),
    ],
)
def test_intervals_overlap(first, second, expected):
    assert intervals_overlap(*first, *second) is expected


def test_availability_uses_supplied_reservations():
    reservations = [(utc(8), utc(9)), (utc(10), utc(11))]
    assert is_available(utc(11), utc(12), reservations)
    assert not is_available(utc(10, 30), utc(11, 30), reservations)
    assert is_available(utc(10), utc(11), [])


@pytest.mark.parametrize(
    ("start", "end", "error"),
    [
        (utc(10), utc(10), ValueError),
        (utc(11), utc(10), ValueError),
        (datetime(2026, 10, 30, 10), utc(11), ValueError),
        (utc(10), datetime(2026, 10, 30, 11), ValueError),
        ("2026-10-30T10:00:00Z", utc(11), TypeError),
        (utc(10), None, TypeError),
    ],
)
def test_validate_interval_rejects_invalid_inputs(start, end, error):
    with pytest.raises(error):
        validate_interval(start, end)


def test_overlap_and_availability_reject_invalid_reservations():
    with pytest.raises(ValueError):
        intervals_overlap(utc(10), utc(11), utc(12), utc(12))
    with pytest.raises(ValueError):
        is_available(utc(10), utc(11), [(utc(10), utc(10))])
    with pytest.raises(ValueError):
        is_available(utc(10), utc(11), [(utc(10), utc(11)), (utc(12), utc(12))])


def test_timezones_are_compared_as_instants():
    plus_two = timezone(timedelta(hours=2))
    overlapping = (
        datetime(2026, 10, 30, 12, 30, tzinfo=plus_two),
        datetime(2026, 10, 30, 13, 30, tzinfo=plus_two),
    )
    consecutive = (
        datetime(2026, 10, 30, 13, tzinfo=plus_two),
        datetime(2026, 10, 30, 14, tzinfo=plus_two),
    )
    assert intervals_overlap(utc(10), utc(11), *overlapping)
    assert not intervals_overlap(utc(10), utc(11), *consecutive)
    assert not is_available(utc(10), utc(11), [overlapping])
    assert is_available(utc(10), utc(11), [consecutive])


def test_validation_uses_absolute_time_across_timezones():
    plus_two = timezone(timedelta(hours=2))
    same_instant = datetime(2026, 10, 30, 12, tzinfo=plus_two)
    with pytest.raises(ValueError):
        validate_interval(utc(10), same_instant)
