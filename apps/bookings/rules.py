"""Regras de horários de reservas, sem dependência de banco ou Django."""

from collections.abc import Iterable
from datetime import UTC, datetime


def _validated_bounds(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise TypeError("Início e fim devem ser datetime.")
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Início e fim devem ter timezone.")

    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    if start_utc >= end_utc:
        raise ValueError("O início deve ser anterior ao fim.")
    return start_utc, end_utc


def validate_interval(start: datetime, end: datetime) -> None:
    """Rejeita datetimes sem timezone e intervalos vazios ou invertidos."""
    _validated_bounds(start, end)


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    """Indica se dois intervalos válidos [início, fim) compartilham tempo."""
    first_start_utc, first_end_utc = _validated_bounds(first_start, first_end)
    second_start_utc, second_end_utc = _validated_bounds(second_start, second_end)
    return first_start_utc < second_end_utc and second_start_utc < first_end_utc


def is_available(
    start: datetime,
    end: datetime,
    reservations: Iterable[tuple[datetime, datetime]],
) -> bool:
    """Verifica intervalos fornecidos, já filtrados por espaço e estado ativo."""
    start_utc, end_utc = _validated_bounds(start, end)
    available = True
    for reserved_start, reserved_end in reservations:
        reserved_start_utc, reserved_end_utc = _validated_bounds(
            reserved_start, reserved_end
        )
        if start_utc < reserved_end_utc and reserved_start_utc < end_utc:
            available = False
    return available
