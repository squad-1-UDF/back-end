"""Camada HTTP provisória de UC001, sem definir o modelo de identidade."""

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class LoginPayload(serializers.Serializer):
    identifier = serializers.CharField(trim_whitespace=False)
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_identifier(self, value):
        if not value.strip():
            raise serializers.ValidationError("Este campo não pode estar vazio.")
        return value

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Envie um objeto JSON."]}
            )
        if set(data) != {"identifier", "password"}:
            raise serializers.ValidationError(
                {"non_field_errors": ["Informe apenas identifier e password."]}
            )
        if not all(isinstance(data[field], str) for field in data):
            raise serializers.ValidationError(
                {"non_field_errors": ["Os campos devem ser texto."]}
            )
        return super().to_internal_value(data)


def authenticate_identifier(request, identifier, password):
    """Ponto único para adaptar USERNAME_FIELD/backend após a decisão de identidade."""
    username_field = get_user_model().USERNAME_FIELD
    return authenticate(
        request._request, password=password, **{username_field: identifier}
    )


@require_GET
@never_cache
@ensure_csrf_cookie
def csrf_cookie(request):
    """Emite o cookie CSRF também para visitantes anônimos, sem consultar o banco."""
    return HttpResponse(status=204)


def csrf_failure(request, reason=""):
    """Resposta genérica para falhas de CSRF, sem expor o motivo interno."""
    return JsonResponse({"error": "CSRF inválido ou ausente."}, status=403)


# APIView.as_view() é csrf_exempt; a proteção em dispatch executa mesmo assim.
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser,)
    http_method_names = ("post", "options")

    def post(self, request):
        payload = LoginPayload(data=request.data)
        payload.is_valid(raise_exception=True)
        user = authenticate_identifier(request, **payload.validated_data)
        if user is None or not getattr(user, "is_active", True):
            return Response(
                {"error": "Credenciais inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request._request, user)
        return Response({"user": {"id": user.pk}})


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("post", "options")

    def post(self, request):
        if request.data != {}:
            raise serializers.ValidationError("Envie um objeto JSON vazio.")
        logout(request._request)
        return Response({"status": "signed_out"})


class MeView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "options")

    def get(self, request):
        return Response({"id": request.user.pk})
