from django.http import HttpResponseNotAllowed, JsonResponse
from django.urls import path


def health(request):
    """Verifica apenas que a API está respondendo (não verifica o banco)."""
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse({"status": "ok", "service": "labtech-api"})


urlpatterns = [
    path("api/v1/health/", health, name="api-health"),
]
