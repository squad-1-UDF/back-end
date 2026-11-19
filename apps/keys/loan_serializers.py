"""Corpos e respostas HTTP de empréstimos e consultas de chaves."""

from rest_framework import serializers


class StrictPositiveIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:  # JSON bool não é um identificador inteiro
            raise serializers.ValidationError("Informe um inteiro.")
        return super().to_internal_value(data)


class CheckoutPayload(serializers.Serializer):
    key_id = StrictPositiveIntegerField(min_value=1)
    responsible_user_id = StrictPositiveIntegerField(min_value=1)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Envie um objeto JSON."]}
            )
        if set(data) != {"key_id", "responsible_user_id"}:
            raise serializers.ValidationError(
                {"non_field_errors": ["Informe apenas key_id e responsible_user_id."]}
            )
        return super().to_internal_value(data)


class CheckoutResponse(serializers.Serializer):
    id = serializers.IntegerField()
    key_id = serializers.IntegerField()
    responsible_user_id = serializers.IntegerField(source="responsible_id")
    checked_out_at = serializers.DateTimeField()
    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        return "active"


class ReturnResponse(serializers.Serializer):
    id = serializers.IntegerField()
    returned_at = serializers.DateTimeField()
    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        return "returned"


class MovementResponse(serializers.Serializer):
    type = serializers.CharField(source="kind")
    loan_id = serializers.IntegerField()
    occurred_at = serializers.DateTimeField()
