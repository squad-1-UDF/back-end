"""Corpos e respostas HTTP de empréstimos e consultas de chaves."""

from rest_framework import serializers


def display_name(user):
    return user.get_full_name() or user.username


class StrictPositiveIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:  # JSON bool não é um identificador inteiro
            raise serializers.ValidationError("Informe um inteiro.")
        return super().to_internal_value(data)


class QueryFilters(serializers.Serializer):
    """Rejeita parâmetros desconhecidos ou repetidos na query string."""

    def to_internal_value(self, data):
        if set(data) - set(self.fields) or any(
            len(data.getlist(field)) != 1 for field in data
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Filtros inválidos ou duplicados."]}
            )
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


class LoanFilters(QueryFilters):
    status = serializers.ChoiceField(choices=["active", "returned"], required=False)
    key_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)
    space_id = serializers.IntegerField(
        min_value=1, max_value=2**63 - 1, required=False
    )
    responsible_user_id = serializers.IntegerField(
        min_value=1, max_value=2**31 - 1, required=False
    )
    limit = serializers.IntegerField(min_value=1, max_value=100, default=100)
    offset = serializers.IntegerField(min_value=0, default=0)


class LoanOut(serializers.Serializer):
    """Empréstimo completo; esperar select_related de key__space e responsible."""

    id = serializers.IntegerField()
    key_id = serializers.IntegerField()
    key_label = serializers.CharField(source="key.label")
    space_id = serializers.IntegerField(source="key.space_id")
    space_code = serializers.CharField(source="key.space.code")
    responsible_user_id = serializers.IntegerField(source="responsible_id")
    responsible_name = serializers.SerializerMethodField()
    checkout_operator_id = serializers.IntegerField()
    checked_out_at = serializers.DateTimeField()
    returned_at = serializers.DateTimeField(allow_null=True)
    return_operator_id = serializers.IntegerField(allow_null=True)
    status = serializers.SerializerMethodField()

    def get_responsible_name(self, obj):
        return display_name(obj.responsible)

    def get_status(self, obj):
        return "active" if obj.returned_at is None else "returned"


class MovementResponse(serializers.Serializer):
    type = serializers.CharField(source="kind")
    loan_id = serializers.IntegerField()
    occurred_at = serializers.DateTimeField()
