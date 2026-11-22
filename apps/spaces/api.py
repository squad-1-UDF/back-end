from typing import ClassVar

from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from psycopg.errors import UniqueViolation
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.spaces.models import Space
from apps.spaces.serializers import SpaceFilters, SpaceSerializer

# spaces_space_code_key: unicidade exata (0001); spaces_space_code_normalized_uniq:
# sem diferenciar maiúsculas nem espaços nas pontas (0002_integridade, P7).
DUPLICATE_CODE_CONSTRAINTS = frozenset(
    {"spaces_space_code_key", "spaces_space_code_normalized_uniq"}
)


def is_duplicate_code(error):
    cause = error.__cause__
    return isinstance(cause, UniqueViolation) and (
        cause.diag.constraint_name in DUPLICATE_CODE_CONSTRAINTS
    )


def duplicate_code_response():
    return Response(
        {
            "error": {
                "code": "DUPLICATE_CODE",
                "message": "Já existe um espaço com este código.",
            }
        },
        status=status.HTTP_409_CONFLICT,
    )


def get_space(space_id):
    if space_id > 2**63 - 1:
        raise Http404
    return get_object_or_404(Space, pk=space_id)


class SpaceAPIView(APIView):
    authentication_classes: ClassVar = (SessionAuthentication,)
    permission_classes: ClassVar = [IsAuthenticated]
    parser_classes: ClassVar = (JSONParser,)

    def get_permissions(self):
        permissions = (
            (IsAuthenticated, IsAdminUser)
            if self.request.method in ("POST", "PATCH")
            else (IsAuthenticated,)
        )
        return [permission() for permission in permissions]

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
class SpaceListCreateView(SpaceAPIView):
    http_method_names: ClassVar = ("get", "post", "options")

    def get(self, request):
        filters = SpaceFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        spaces = Space.objects.order_by("id")
        if "is_active" in values:
            spaces = spaces.filter(is_active=values["is_active"] == "true")
        if "kind" in values:
            spaces = spaces.filter(kind=values["kind"])
        return Response(SpaceSerializer(spaces, many=True).data)

    def post(self, request):
        serializer = SpaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                space = Space.objects.create(**serializer.validated_data)
        except IntegrityError as error:
            if not is_duplicate_code(error):
                raise
            return duplicate_code_response()
        return Response(
            SpaceSerializer(space).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class SpaceDetailView(SpaceAPIView):
    http_method_names: ClassVar = ("get", "patch", "options")

    def get(self, request, space_id):
        space = get_space(space_id)
        return Response(SpaceSerializer(space).data)

    def patch(self, request, space_id):
        space = get_space(space_id)
        serializer = SpaceSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(space, field, value)
        try:
            with transaction.atomic():
                space.save(update_fields=list(serializer.validated_data))
        except IntegrityError as error:
            if not is_duplicate_code(error):
                raise
            return duplicate_code_response()
        return Response(SpaceSerializer(space).data)
