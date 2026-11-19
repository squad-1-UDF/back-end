"""Operações de reservas com serialização por espaço e exclusão PostgreSQL."""

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.rules import is_available, validate_interval
from apps.spaces.models import Space


class BookingAlreadyCancelled(Exception):
    """A reserva já foi cancelada e seu registro não pode ser reescrito."""


class BookingNotVisible(Exception):
    """O usuário não pode operar esta reserva."""


def occupied_bookings(*, space_id, start_at, end_at):
    validate_interval(start_at, end_at)
    return Booking.objects.filter(
        space_id=space_id,
        status=Booking.Status.ACTIVE,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).order_by("start_at", "end_at", "id")


def booking_available(*, space_id, start_at, end_at):
    bookings = occupied_bookings(space_id=space_id, start_at=start_at, end_at=end_at)
    return is_available(
        start_at, end_at, bookings.values_list("start_at", "end_at")[:1]
    )


@transaction.atomic
def create_booking(*, space, user, start_at, end_at):
    validate_interval(start_at, end_at)
    # Serializa INSERTs do mesmo espaço antes da constraint GiST; NO KEY UPDATE
    # mantém compatibilidade com o KEY SHARE usado pela FK da reserva.
    Space.objects.select_for_update(no_key=True).get(pk=space.pk)
    return Booking.objects.create(
        space=space, user=user, start_at=start_at, end_at=end_at
    )


@transaction.atomic
def cancel_booking(*, booking_id, actor):
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if not actor.is_staff and booking.user_id != actor.pk:
        raise BookingNotVisible
    if booking.status == Booking.Status.CANCELLED:
        raise BookingAlreadyCancelled
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_at"])
    return booking
