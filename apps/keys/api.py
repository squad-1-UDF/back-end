"""HTTP do cadastro de chaves (UC004).

Mantém os nomes de views e rotas propostos no PR feature/keys-api
(KeyListCreateView, KeyDetailView, keys-list e keys-detail), agora com banco.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.keys.loan_views import LoanAPIView, conflict
from apps.keys.serializers import KeyFilters, KeyOut, KeySerializer
from apps.keys.services import (
    DuplicateKeyLabel,
    KeySpaceLocked,
    create_key,
    keys_with_active_loan,
    update_key,
)
from apps.spaces.models import Space

MAX_BIGINT = 2**63 - 1


def get_key_out(key_id):
    if key_id > MAX_BIGINT:
        raise Http404
    return get_object_or_404(keys_with_active_loan(), pk=key_id)


def duplicate_label_error():
    return serializers.ValidationError(
        {"label": ["Já existe uma chave com este rótulo."]}
    )


class KeyAPIView(LoanAPIView):
    permission_classes = (IsAuthenticated, IsAdminUser)


@method_decorator(csrf_protect, name="dispatch")
class KeyListCreateView(KeyAPIView):
    http_method_names = ("get", "post", "options")

    def get(self, request):
        filters = KeyFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        keys = keys_with_active_loan()
        if "space_id" in values:
            keys = keys.filter(space_id=values["space_id"])
        if "status" in values:
            keys = keys.filter(status=values["status"])
        if "has_active_loan" in values:
            keys = keys.filter(is_loaned=values["has_active_loan"])
        return Response(KeyOut(keys, many=True).data)

    def post(self, request):
        payload = KeySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        space = get_object_or_404(Space, pk=values["space_id"])
        try:
            key = create_key(
                space=space,
                label=values["label"],
                status=values.get("status", "available"),
            )
        except DuplicateKeyLabel:
            raise duplicate_label_error() from None
        return Response(
            KeyOut(get_key_out(key.pk)).data, status=status.HTTP_201_CREATED
        )


@method_decorator(csrf_protect, name="dispatch")
class KeyDetailView(KeyAPIView):
    http_method_names = ("get", "patch", "options")

    def get(self, request, key_id):
        return Response(KeyOut(get_key_out(key_id)).data)

    def patch(self, request, key_id):
        get_key_out(key_id)
        payload = KeySerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        changes = dict(payload.validated_data)
        if "space_id" in changes:
            changes["space"] = get_object_or_404(Space, pk=changes.pop("space_id"))
        try:
            update_key(key_id=key_id, changes=changes)
        except DuplicateKeyLabel:
            raise duplicate_label_error() from None
        except KeySpaceLocked:
            return conflict(
                "KEY_SPACE_LOCKED",
                "Chave com histórico de empréstimo não pode mudar de espaço.",
                details={"key_id": key_id},
            )
        return Response(KeyOut(get_key_out(key_id)).data)
