"""HTTP para retirada, devolução e leitura do histórico de chaves."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.keys.loan_serializers import (
    CheckoutPayload,
    LoanFilters,
    LoanOut,
    MovementResponse,
)
from apps.keys.models import Key, KeyLoan
from apps.keys.services import (
    KeyNotAvailable,
    checkout_key,
    has_active_loan,
    loans_with_relations,
    movements_for_key,
    return_key,
)


def conflict(code, message, *, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return Response({"error": error}, status=status.HTTP_409_CONFLICT)


def is_active_loan_constraint(exc):
    cause = exc.__cause__
    diag = getattr(cause, "diag", None)
    return getattr(diag, "constraint_name", None) == "keys_one_active_loan_per_key"


class LoanAPIView(APIView):
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
class CheckoutView(LoanAPIView):
    """GET lista empréstimos; POST registra retirada. Ambos exigem staff."""

    permission_classes = (IsAuthenticated, IsAdminUser)
    http_method_names = ("get", "post", "options")

    def get(self, request):
        filters = LoanFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        loans = loans_with_relations()
        if "status" in values:
            loans = loans.filter(returned_at__isnull=values["status"] == "active")
        if "key_id" in values:
            loans = loans.filter(key_id=values["key_id"])
        if "space_id" in values:
            loans = loans.filter(key__space_id=values["space_id"])
        if "responsible_user_id" in values:
            loans = loans.filter(responsible_id=values["responsible_user_id"])
        page = loans[values["offset"] : values["offset"] + values["limit"]]
        return Response(LoanOut(page, many=True).data)

    def post(self, request):
        payload = CheckoutPayload(data=request.data)
        payload.is_valid(raise_exception=True)
        key_id = payload.validated_data["key_id"]
        responsible_id = payload.validated_data["responsible_user_id"]
        get_object_or_404(Key, pk=key_id)
        responsible = get_object_or_404(get_user_model(), pk=responsible_id)

        try:
            loan = checkout_key(
                key_id=key_id, responsible=responsible, operator=request.user
            )
        except KeyNotAvailable as exc:
            return conflict(
                "KEY_UNAVAILABLE",
                "Chave fora de uso para retirada.",
                details={"key_id": key_id, "status": exc.status},
            )
        except IntegrityError as exc:
            if not is_active_loan_constraint(exc):
                raise
            return conflict(
                "KEY_UNAVAILABLE",
                "Chave com empréstimo ativo.",
                details={"key_id": key_id},
            )
        except ValueError as exc:
            if str(exc) != "Chave indisponível: empréstimo ativo.":
                raise
            return conflict(
                "KEY_UNAVAILABLE",
                "Chave com empréstimo ativo.",
                details={"key_id": key_id},
            )
        return Response(
            LoanOut(loans_with_relations().get(pk=loan.pk)).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class ReturnView(LoanAPIView):
    permission_classes = (IsAuthenticated, IsAdminUser)
    http_method_names = ("post", "options")

    def post(self, request, loan_id):
        if not request._request.body or request.data != {}:
            raise serializers.ValidationError("Envie um objeto JSON vazio.")
        get_object_or_404(KeyLoan, pk=loan_id)

        try:
            loan = return_key(loan_id=loan_id, operator=request.user)
        except ValueError as exc:
            if str(exc) != "Empréstimo inexistente ou já encerrado.":
                raise
            return conflict("LOAN_ALREADY_RETURNED", "Empréstimo já encerrado.")
        return Response(LoanOut(loans_with_relations().get(pk=loan.pk)).data)


class LoanAvailabilityView(LoanAPIView):
    http_method_names = ("get", "options")

    def get(self, request, key_id):
        key = get_object_or_404(Key, pk=key_id)
        return Response({"key_id": key.pk, "has_active_loan": has_active_loan(key)})


class MovementsView(LoanAPIView):
    http_method_names = ("get", "options")

    def get(self, request, key_id):
        key = get_object_or_404(Key, pk=key_id)
        events = MovementResponse(movements_for_key(key), many=True).data
        return Response({"key_id": key.pk, "events": events})
