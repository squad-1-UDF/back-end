"""Reservas persistidas com proteção de sobreposição no PostgreSQL."""

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    DateTimeRangeField,
    RangeBoundary,
    RangeOperators,
)
from django.db import models
from django.db.models import F, Func, Q


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Booking(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        CANCELLED = "cancelled", "Cancelada"

    id = models.BigAutoField(primary_key=True)
    space = models.ForeignKey(
        "spaces.Space", on_delete=models.PROTECT, related_name="bookings"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=9, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=Q(start_at__lt=F("end_at")),
                name="bookings_start_before_end",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "cancelled"]),
                name="bookings_status_valid",
            ),
            models.CheckConstraint(
                condition=(Q(status="active") & Q(cancelled_at__isnull=True))
                | (Q(status="cancelled") & Q(cancelled_at__isnull=False)),
                name="bookings_cancelled_at_matches_status",
            ),
            ExclusionConstraint(
                name="bookings_active_no_overlap",
                expressions=[
                    ("space", RangeOperators.EQUAL),
                    (
                        TsTzRange("start_at", "end_at", RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status="active"),
            ),
        ]
