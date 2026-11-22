"""Contrato HTTP do cadastro de chaves (UC004).

Parte da estrutura inicial proposta no PR feature/keys-api (KeySerializer,
KeyListCreateView e KeyDetailView), agora ligada ao banco.
"""

from rest_framework import serializers

from apps.keys.loan_serializers import (
    QueryFilters,
    StrictPositiveIntegerField,
    display_name,
)
from apps.keys.models import Key

KEY_STATUSES = [choice for choice, _ in Key.Status.choices]


class KeySerializer(serializers.Serializer):
    """Entrada de POST /keys/ e, com partial=True, de PATCH /keys/{id}/."""

    space_id = StrictPositiveIntegerField(min_value=1, max_value=2**63 - 1)
    label = serializers.CharField(
        max_length=40, allow_blank=False, trim_whitespace=True
    )
    status = serializers.ChoiceField(choices=KEY_STATUSES, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Envie um objeto JSON."]}
            )
        extra = set(data) - {"space_id", "label", "status"}
        if extra:
            raise serializers.ValidationError(
                {"non_field_errors": ["Informe apenas space_id, label e status."]}
            )
        return super().to_internal_value(data)


class BooleanQueryField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(choices=["true", "false"], **kwargs)

    def to_internal_value(self, data):
        return super().to_internal_value(data) == "true"


class KeyFilters(QueryFilters):
    space_id = serializers.IntegerField(
        min_value=1, max_value=2**63 - 1, required=False
    )
    status = serializers.ChoiceField(choices=KEY_STATUSES, required=False)
    has_active_loan = BooleanQueryField(required=False)


class ActiveLoanOut(serializers.Serializer):
    id = serializers.IntegerField()
    responsible_user_id = serializers.IntegerField(source="responsible_id")
    responsible_name = serializers.SerializerMethodField()
    checked_out_at = serializers.DateTimeField()

    def get_responsible_name(self, obj):
        return display_name(obj.responsible)


class KeyOut(serializers.Serializer):
    """Espera chaves vindas de services.keys_with_active_loan()."""

    id = serializers.IntegerField()
    space_id = serializers.IntegerField()
    space_code = serializers.CharField(source="space.code")
    label = serializers.CharField()
    status = serializers.CharField()
    has_active_loan = serializers.SerializerMethodField()
    active_loan = serializers.SerializerMethodField()

    def _active(self, obj):
        return obj.active_loans[0] if obj.active_loans else None

    def get_has_active_loan(self, obj):
        return self._active(obj) is not None

    def get_active_loan(self, obj):
        loan = self._active(obj)
        return None if loan is None else ActiveLoanOut(loan).data
