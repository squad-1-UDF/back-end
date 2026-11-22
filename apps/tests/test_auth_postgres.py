"""UC001 com auth.User e sessões persistidas no PostgreSQL de teste."""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse

database = settings.DATABASES["default"]
if database["ENGINE"] == "django.db.backends.postgresql":
    allowed_targets = {
        ("labtech_local", "127.0.0.1", "55432"),
        ("labtech_local", "127.0.0.1", "56432"),
        ("labtech_ci", "127.0.0.1", "5432"),
    }
    target = (database["NAME"], database["HOST"], str(database["PORT"]))
    if target not in allowed_targets or database["TEST"]["NAME"] != (
        f"test_{database['NAME']}"
    ):
        raise RuntimeError("UC001 integrada exige o PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC001 integrada exige DB_NAME apontando ao PostgreSQL local/de CI",
    ),
]


def post_json(client, url, payload, *, csrf=None):
    headers = {} if csrf is None else {"HTTP_X_CSRFTOKEN": csrf}
    return client.post(url, data=payload, content_type="application/json", **headers)


@pytest.mark.parametrize("is_staff", [False, True])
def test_uc001_real_login_session_and_logout(is_staff):
    user_model = get_user_model()
    assert user_model._meta.label == "auth.User"
    user = user_model.objects.create_user(
        username="ana", password="senha-forte-123", is_staff=is_staff
    )
    assert user.password != "senha-forte-123"
    assert user.check_password("senha-forte-123")

    client = Client(enforce_csrf_checks=True)
    login_url = reverse("auth-login")
    assert client.get(reverse("auth-me")).status_code == 403
    csrf_response = client.get(reverse("auth-csrf"))
    assert csrf_response.status_code == 204
    assert "csrftoken" in client.cookies
    assert "sessionid" not in client.cookies

    payload = {"identifier": "ana", "password": "senha-forte-123"}
    assert post_json(client, login_url, payload).status_code == 403
    csrf = client.cookies["csrftoken"].value
    assert post_json(client, login_url, payload, csrf="b" * 32).status_code == 403
    bad_login = post_json(
        client,
        login_url,
        {"identifier": "ana", "password": "incorreta"},
        csrf=csrf,
    )
    assert bad_login.status_code == 401
    assert "sessionid" not in client.cookies

    login_response = post_json(client, login_url, payload, csrf=csrf)
    assert login_response.status_code == 200
    assert login_response.json() == {"user": {"id": user.pk}}
    session_key = client.cookies["sessionid"].value
    session = Session.objects.get(session_key=session_key)
    assert session.get_decoded()["_auth_user_id"] == str(user.pk)

    later_client = Client(enforce_csrf_checks=True)
    later_client.cookies["sessionid"] = session_key
    me = later_client.get(reverse("auth-me"))
    assert me.status_code == 200
    assert me.json() == {
        "id": user.pk,
        "username": "ana",
        "name": "ana",
        "email": "",
        "role": "employee" if is_staff else "student",
        "is_staff": is_staff,
    }

    # O login renova o token CSRF; use o cookie atual para o logout.
    logout = post_json(
        client,
        reverse("auth-logout"),
        {},
        csrf=client.cookies["csrftoken"].value,
    )
    assert logout.status_code == 200
    assert logout.json() == {"status": "signed_out"}
    assert not Session.objects.filter(session_key=session_key).exists()
    assert later_client.get(reverse("auth-me")).status_code == 403


def test_inactive_user_cannot_log_in():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="inativa", password="senha-forte-123"
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    response = post_json(
        client,
        reverse("auth-login"),
        {"identifier": "inativa", "password": "senha-forte-123"},
        csrf=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 401
    assert response.json() == {"error": "Credenciais inválidas."}
    assert "sessionid" not in client.cookies
    assert client.get(reverse("auth-me")).status_code == 403
