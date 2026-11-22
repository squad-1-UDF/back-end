"""Entrada e saída de UC002 (usuários e perfis)."""

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.roles import ROLES, get_role

NAME_PART_MAX = 150


def display_name(user):
    return user.get_full_name() or user.username


def split_name(name):
    """Divide ``name`` em ``first_name`` (primeira palavra) e ``last_name``."""
    parts = name.split(maxsplit=1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


class StrictObjectMixin:
    """Recusa corpo que não seja objeto JSON e campos desconhecidos."""

    allowed_fields = ()

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Envie um objeto JSON."]}
            )
        unknown = sorted(set(data) - set(self.allowed_fields))
        if unknown:
            raise serializers.ValidationError(
                {field: ["Campo não permitido."] for field in unknown}
            )
        return super().to_internal_value(data)


class NameField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(allow_blank=True, trim_whitespace=True, **kwargs)

    def to_internal_value(self, data):
        value = " ".join(super().to_internal_value(data).split())
        first, last = split_name(value)
        if len(first) > NAME_PART_MAX or len(last) > NAME_PART_MAX:
            raise serializers.ValidationError("Nome muito longo.")
        return value


def normalize_email(value):
    return BaseUserManager.normalize_email(value.strip())


def check_password(password, user):
    try:
        password_validation.validate_password(password, user=user)
    except DjangoValidationError as error:
        raise serializers.ValidationError({"password": list(error.messages)}) from None


class UserCreatePayload(StrictObjectMixin, serializers.Serializer):
    allowed_fields = ("username", "name", "email", "role", "password")

    username = serializers.CharField(
        max_length=150, validators=[UnicodeUsernameValidator()]
    )
    name = NameField(required=False, default="")
    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=ROLES)
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return normalize_email(value)

    def validate(self, attrs):
        first, last = split_name(attrs["name"])
        candidate = get_user_model()(
            username=attrs["username"],
            email=attrs["email"],
            first_name=first,
            last_name=last,
        )
        check_password(attrs["password"], candidate)
        return attrs


class UserUpdatePayload(StrictObjectMixin, serializers.Serializer):
    allowed_fields = ("name", "email", "role", "is_active", "password")

    name = NameField(required=False)
    email = serializers.EmailField(max_length=254, required=False)
    role = serializers.ChoiceField(choices=ROLES, required=False)
    is_active = serializers.BooleanField(required=False)
    password = serializers.CharField(
        trim_whitespace=False, write_only=True, required=False
    )

    def validate_email(self, value):
        return normalize_email(value)

    def validate(self, attrs):
        if "password" in attrs:
            check_password(attrs["password"], self.instance)
        return attrs


class UserFilters(serializers.Serializer):
    fields_allowed = ("role", "is_active", "q", "limit", "offset")

    role = serializers.ChoiceField(choices=ROLES, required=False)
    # ChoiceField: o BooleanField do DRF trata filtro ausente em query como False.
    is_active = serializers.ChoiceField(choices=["true", "false"], required=False)
    q = serializers.CharField(max_length=150, required=False, allow_blank=True)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=100)
    offset = serializers.IntegerField(min_value=0, default=0)

    def to_internal_value(self, data):
        if set(data) - set(self.fields_allowed) or any(
            len(data.getlist(field)) != 1 for field in data
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Filtros inválidos ou duplicados."]}
            )
        return super().to_internal_value(data)


class UserResponse(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    name = serializers.SerializerMethodField()
    email = serializers.EmailField()
    role = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()
    date_joined = serializers.DateTimeField()

    def get_name(self, user):
        return display_name(user)

    def get_role(self, user):
        return get_role(user)


class MeResponse(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    username = serializers.CharField()
    name = serializers.SerializerMethodField()
    email = serializers.CharField()
    role = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField()

    def get_name(self, user):
        return display_name(user)

    def get_role(self, user):
        return get_role(user)
