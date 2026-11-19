"""Contrato HTTP de reservas e disponibilidade de espaços."""

import re
from datetime import timedelta

from rest_framework import serializers

from apps.bookings.rules import validate_interval

ISO_WITH_OFFSET = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
MAX_QUERY_WINDOW = timedelta(days=31)


class StrictPositiveIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            raise serializers.ValidationError("Informe um inteiro.")
        return super().to_internal_value(data)


class AwareDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, data):
        if not isinstance(data, str) or not ISO_WITH_OFFSET.fullmatch(data):
            raise serializers.ValidationError(
                "Informe data/hora ISO 8601 com timezone explícito."
            )
        return super().to_internal_value(data)


class BookingCreatePayload(serializers.Serializer):
    space_id = StrictPositiveIntegerField(min_value=1)
    start_at = AwareDateTimeField()
    end_at = AwareDateTimeField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {
            "space_id",
            "start_at",
            "end_at",
        }:
            raise serializers.ValidationError(
                {"non_field_errors": ["Informe apenas space_id, start_at e end_at."]}
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        try:
            validate_interval(attrs["start_at"], attrs["end_at"])
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        return attrs


class WindowQuery(serializers.Serializer):
    start_at = AwareDateTimeField()
    end_at = AwareDateTimeField()

    def to_internal_value(self, data):
        if set(data) != {"start_at", "end_at"} or any(
            len(data.getlist(field)) != 1 for field in data
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Informe apenas start_at e end_at uma vez."]}
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        try:
            validate_interval(attrs["start_at"], attrs["end_at"])
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        if attrs["end_at"] - attrs["start_at"] > MAX_QUERY_WINDOW:
            raise serializers.ValidationError(
                {"non_field_errors": ["A consulta deve cobrir no máximo 31 dias."]}
            )
        return attrs


class BookingFilters(serializers.Serializer):
    space_id = serializers.IntegerField(min_value=1, required=False)
    status = serializers.ChoiceField(choices=["active", "cancelled"], required=False)
    scope = serializers.ChoiceField(choices=["mine", "all"], default="mine")
    limit = serializers.IntegerField(min_value=1, max_value=100, default=100)
    offset = serializers.IntegerField(min_value=0, default=0)

    def to_internal_value(self, data):
        if set(data) - {"space_id", "status", "scope", "limit", "offset"} or any(
            len(data.getlist(field)) != 1 for field in data
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Filtros inválidos ou duplicados."]}
            )
        return super().to_internal_value(data)


class BookingResponse(serializers.Serializer):
    id = serializers.IntegerField()
    space_id = serializers.IntegerField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    cancelled_at = serializers.DateTimeField(allow_null=True)


class CancellationResponse(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    cancelled_at = serializers.DateTimeField()


class AvailabilityResponse(serializers.Serializer):
    space_id = serializers.IntegerField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    available = serializers.BooleanField()


class OccupiedWindowResponse(serializers.Serializer):
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()


class AgendaResponse(serializers.Serializer):
    space_id = serializers.IntegerField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    occupied = OccupiedWindowResponse(many=True)
