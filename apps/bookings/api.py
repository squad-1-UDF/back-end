"""API HTTP de reservas, disponibilidade e agenda."""

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.bookings.serializers import (
    AgendaResponse,
    AvailabilityResponse,
    BookingCreatePayload,
    BookingFilters,
    BookingResponse,
    CancellationResponse,
    WindowQuery,
)
from apps.bookings.services import (
    BookingAlreadyCancelled,
    BookingNotVisible,
    booking_available,
    cancel_booking,
    create_booking,
    occupied_bookings,
)
from apps.spaces.models import Space

MAX_AGENDA_EVENTS = 1000


def conflict(code, message, *, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return Response({"error": error}, status=status.HTTP_409_CONFLICT)


def is_booking_conflict(exc):
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == "bookings_active_no_overlap"


class BookingAPIView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        errors = {
            400: ("INVALID_REQUEST", "Entrada inválida."),
            403: ("FORBIDDEN", "Acesso não permitido."),
            404: ("NOT_FOUND", "Recurso não encontrado."),
        }
        if response.status_code in errors:
            code, message = errors[response.status_code]
            error = {"code": code, "message": message}
            if response.status_code == 400:
                error["details"] = response.data
            response.data = {"error": error}
        return response


@method_decorator(csrf_protect, name="dispatch")
class BookingListCreateView(BookingAPIView):
    http_method_names = ("get", "post", "options")

    def get(self, request):
        filters = BookingFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        if values["scope"] == "all" and not request.user.is_staff:
            raise PermissionDenied
        bookings = Booking.objects.all()
        if values["scope"] == "mine":
            bookings = bookings.filter(user=request.user)
        if "space_id" in values:
            bookings = bookings.filter(space_id=values["space_id"])
        if "status" in values:
            bookings = bookings.filter(status=values["status"])
        page = bookings.order_by("start_at", "id")[
            values["offset"] : values["offset"] + values["limit"]
        ]
        return Response(BookingResponse(page, many=True).data)

    def post(self, request):
        payload = BookingCreatePayload(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        space = get_object_or_404(Space, pk=values["space_id"])
        try:
            booking = create_booking(
                space=space,
                user=request.user,
                start_at=values["start_at"],
                end_at=values["end_at"],
            )
        except IntegrityError as exc:
            if not is_booking_conflict(exc):
                raise
            return conflict(
                "BOOKING_CONFLICT",
                "Horário indisponível para o espaço.",
                details={"space_id": space.pk},
            )
        return Response(BookingResponse(booking).data, status=status.HTTP_201_CREATED)


class BookingDetailView(BookingAPIView):
    http_method_names = ("get", "options")

    def get(self, request, booking_id):
        bookings = Booking.objects.all()
        if not request.user.is_staff:
            bookings = bookings.filter(user=request.user)
        booking = get_object_or_404(bookings, pk=booking_id)
        return Response(BookingResponse(booking).data)


@method_decorator(csrf_protect, name="dispatch")
class BookingCancelView(BookingAPIView):
    http_method_names = ("post", "options")

    def post(self, request, booking_id):
        if not request._request.body or request.data != {}:
            raise serializers.ValidationError("Envie um objeto JSON vazio.")
        bookings = Booking.objects.all()
        if not request.user.is_staff:
            bookings = bookings.filter(user=request.user)
        get_object_or_404(bookings, pk=booking_id)
        try:
            booking = cancel_booking(booking_id=booking_id, actor=request.user)
        except BookingNotVisible:
            raise NotFound from None
        except BookingAlreadyCancelled:
            return conflict("BOOKING_ALREADY_CANCELLED", "Reserva já cancelada.")
        return Response(CancellationResponse(booking).data)


class BookingAvailabilityView(BookingAPIView):
    http_method_names = ("get", "options")

    def get(self, request, space_id):
        space = get_object_or_404(Space, pk=space_id)
        window = WindowQuery(data=request.query_params)
        window.is_valid(raise_exception=True)
        values = window.validated_data
        available = booking_available(space_id=space.pk, **values)
        return Response(
            AvailabilityResponse(
                {**values, "space_id": space.pk, "available": available}
            ).data
        )


class BookingAgendaView(BookingAPIView):
    http_method_names = ("get", "options")

    def get(self, request, space_id):
        space = get_object_or_404(Space, pk=space_id)
        window = WindowQuery(data=request.query_params)
        window.is_valid(raise_exception=True)
        values = window.validated_data
        occupied = list(
            occupied_bookings(space_id=space.pk, **values).values("start_at", "end_at")[
                : MAX_AGENDA_EVENTS + 1
            ]
        )
        if len(occupied) > MAX_AGENDA_EVENTS:
            raise serializers.ValidationError(
                {"non_field_errors": ["Reduza o intervalo da agenda."]}
            )
        return Response(
            AgendaResponse({**values, "space_id": space.pk, "occupied": occupied}).data
        )
