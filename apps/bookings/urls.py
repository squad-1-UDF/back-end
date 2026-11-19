"""Rotas de reservas, disponibilidade e agenda."""

from django.urls import path

from apps.bookings.api import (
    BookingAgendaView,
    BookingAvailabilityView,
    BookingCancelView,
    BookingDetailView,
    BookingListCreateView,
)

urlpatterns = [
    path("bookings/", BookingListCreateView.as_view(), name="bookings-list"),
    path(
        "bookings/<int:booking_id>/cancel/",
        BookingCancelView.as_view(),
        name="bookings-cancel",
    ),
    path(
        "bookings/<int:booking_id>/",
        BookingDetailView.as_view(),
        name="bookings-detail",
    ),
    path(
        "spaces/<int:space_id>/booking-availability/",
        BookingAvailabilityView.as_view(),
        name="booking-availability",
    ),
    path(
        "spaces/<int:space_id>/booking-agenda/",
        BookingAgendaView.as_view(),
        name="booking-agenda",
    ),
]
