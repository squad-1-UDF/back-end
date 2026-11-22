"""HTTP de UC002: listar, cadastrar, consultar e atualizar usuários (sem DELETE)."""

from typing import ClassVar

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import CharField, Q, Value
from django.db.models.functions import Coalesce, Concat, Lower, NullIf, Trim
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import (
    ADMIN,
    STAFF_ROLES,
    apply_role,
    get_role,
    role_filter,
    with_admin_flag,
)
from apps.accounts.serializers import (
    UserCreatePayload,
    UserFilters,
    UserResponse,
    UserUpdatePayload,
    split_name,
)

# Chave arbitrária do advisory lock que serializa escritas de usuários, para que
# a checagem de unicidade de username/email não sofra corrida entre requisições.
USER_WRITE_LOCK = 2_002_001


class IsStaffRole(BasePermission):
    """Funcionário ou administrador (papel derivado, não só ``is_staff``)."""

    def has_permission(self, request, view):
        return get_role(request.user) in STAFF_ROLES


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return get_role(request.user) == ADMIN


def users_queryset():
    User = get_user_model()
    full_name = Trim(
        Concat("first_name", Value(" "), "last_name", output_field=CharField())
    )
    return with_admin_flag(User.objects.all()).annotate(
        sort_name=Lower(Coalesce(NullIf(full_name, Value("")), "username"))
    )


def get_user(user_id):
    if user_id > 2**31 - 1:
        raise Http404
    return get_object_or_404(users_queryset(), pk=user_id)


def conflict(code, message, field):
    return Response(
        {"error": {"code": code, "message": message, "details": {"field": field}}},
        status=status.HTTP_409_CONFLICT,
    )


def lock_user_writes():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [USER_WRITE_LOCK])


def find_duplicate(*, username=None, email=None, exclude_id=None):
    users = get_user_model().objects.all()
    if exclude_id is not None:
        users = users.exclude(pk=exclude_id)
    if username is not None and users.filter(username__iexact=username).exists():
        return conflict(
            "DUPLICATE_USERNAME", "Já existe um usuário com este username.", "username"
        )
    if email is not None and users.filter(email__iexact=email).exists():
        return conflict(
            "DUPLICATE_EMAIL", "Já existe um usuário com este e-mail.", "email"
        )
    return None


class UserAPIView(APIView):
    authentication_classes: ClassVar = (SessionAuthentication,)
    parser_classes: ClassVar = (JSONParser,)

    def get_permissions(self):
        permissions = (
            (IsAuthenticated, IsAdminRole)
            if self.request.method in ("POST", "PATCH")
            else (IsAuthenticated, IsStaffRole)
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
class UserListCreateView(UserAPIView):
    http_method_names: ClassVar = ("get", "post", "options")

    def get(self, request):
        filters = UserFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        users = users_queryset()
        if "role" in values:
            users = users.filter(role_filter(values["role"]))
        if "is_active" in values:
            users = users.filter(is_active=values["is_active"] == "true")
        if values.get("q", "").strip():
            term = values["q"].strip()
            users = users.filter(
                Q(username__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
            )
        page = users.order_by("sort_name", "id")[
            values["offset"] : values["offset"] + values["limit"]
        ]
        return Response(UserResponse(page, many=True).data)

    def post(self, request):
        payload = UserCreatePayload(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        first, last = split_name(values["name"])
        with transaction.atomic():
            lock_user_writes()
            duplicate = find_duplicate(
                username=values["username"], email=values["email"]
            )
            if duplicate is not None:
                return duplicate
            user = get_user_model().objects.create_user(
                username=values["username"],
                email=values["email"],
                password=values["password"],
                first_name=first,
                last_name=last,
            )
            apply_role(user, values["role"])
            user.save(update_fields=["is_staff"])
        return Response(UserResponse(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class UserDetailView(UserAPIView):
    http_method_names: ClassVar = ("get", "patch", "options")

    def get(self, request, user_id):
        return Response(UserResponse(get_user(user_id)).data)

    def patch(self, request, user_id):
        user = get_user(user_id)
        payload = UserUpdatePayload(user, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        self.check_rules(request.user, user, values)

        with transaction.atomic():
            lock_user_writes()
            if "email" in values:
                duplicate = find_duplicate(email=values["email"], exclude_id=user.pk)
                if duplicate is not None:
                    return duplicate
            update_fields = []
            if "name" in values:
                user.first_name, user.last_name = split_name(values["name"])
                update_fields += ["first_name", "last_name"]
            if "email" in values:
                user.email = values["email"]
                update_fields.append("email")
            if "is_active" in values:
                user.is_active = values["is_active"]
                update_fields.append("is_active")
            if "password" in values:
                user.set_password(values["password"])
                update_fields.append("password")
            if "role" in values:
                apply_role(user, values["role"])
                update_fields.append("is_staff")
            if update_fields:
                user.save(update_fields=update_fields)
        return Response(UserResponse(user).data)

    @staticmethod
    def check_rules(actor, user, values):
        errors = {}
        if user.pk == actor.pk:
            if values.get("is_active") is False:
                errors["is_active"] = ["Você não pode desativar a si mesmo."]
            if values.get("role", ADMIN) != ADMIN:
                errors["role"] = ["Você não pode remover o próprio papel de admin."]
        if user.is_superuser and values.get("role", ADMIN) != ADMIN:
            errors["role"] = ["Superusuário não pode ser rebaixado pela API."]
        if errors:
            raise serializers.ValidationError(errors)
