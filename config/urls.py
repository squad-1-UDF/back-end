from django.http import HttpResponseNotAllowed, JsonResponse
from django.urls import path

from apps.accounts.api import LoginView, LogoutView, MeView, csrf_cookie


def health(request):
    """Verifica apenas que a API está respondendo (não verifica o banco)."""
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse({"status": "ok", "service": "labtech-api"})


urlpatterns = [
    path("api/v1/health/", health, name="api-health"),
    path("api/v1/auth/csrf/", csrf_cookie, name="auth-csrf"),
    path("api/v1/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/v1/auth/me/", MeView.as_view(), name="auth-me"),
]
