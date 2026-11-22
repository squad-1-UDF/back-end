"""UC002 (usuários e perfis) via HTTP, sessão Django e PostgreSQL de teste."""

import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from apps.accounts.roles import ADMIN_GROUP, admin_group, get_role

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
        raise RuntimeError("UC002 HTTP exige PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC002 HTTP exige PostgreSQL local ou da CI",
    ),
]

PASSWORD = "senha-forte-123"
NEW_PASSWORD = "Outra-Senha-Forte-987"
User = get_user_model()


def make_user(username, *, role="student", superuser=False, **extra):
    user = User.objects.create_user(
        username=username,
        password=PASSWORD,
        is_staff=role in ("admin", "employee") or superuser,
        is_superuser=superuser,
        **extra,
    )
    if role == "admin" and not superuser:
        user.groups.add(admin_group())
    return user


def login(user):
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    response = client.post(
        reverse("auth-login"),
        data=json.dumps({"identifier": user.username, "password": PASSWORD}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200
    return client


def post(client, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return client.post(
        reverse("users-list"),
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


def patch(client, user_id, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return client.patch(
        reverse("users-detail", args=[user_id]),
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


def new_user_payload(**overrides):
    payload = {
        "username": "bruno",
        "name": "Bruno Lima",
        "email": "bruno@udf.edu.br",
        "role": "student",
        "password": PASSWORD,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def admin():
    return make_user("chefe", role="admin", first_name="Ana", last_name="Costa")


@pytest.fixture
def admin_client(admin):
    return login(admin)


def test_migration_creates_admin_group():
    assert Group.objects.filter(name=ADMIN_GROUP).exists()


@pytest.mark.parametrize(
    ("is_staff", "is_superuser", "in_group", "expected"),
    [
        (False, False, False, "student"),
        (True, False, False, "employee"),
        (True, False, True, "admin"),
        (False, False, True, "admin"),
        (False, True, False, "admin"),
        (True, True, False, "admin"),
    ],
)
def test_role_mapping(is_staff, is_superuser, in_group, expected):
    user = User.objects.create_user(
        username="pessoa", is_staff=is_staff, is_superuser=is_superuser
    )
    if in_group:
        user.groups.add(admin_group())
    assert get_role(user) == expected


def test_me_returns_profile_with_role(admin, admin_client):
    response = admin_client.get(reverse("auth-me"))
    assert response.status_code == 200
    assert response.json() == {
        "id": admin.pk,
        "username": "chefe",
        "name": "Ana Costa",
        "email": "",
        "role": "admin",
        "is_staff": True,
    }


def test_me_superuser_without_group_is_admin():
    root = make_user("raiz", superuser=True)
    assert login(root).get(reverse("auth-me")).json()["role"] == "admin"


def test_list_permissions():
    student = make_user("aluno")
    employee = make_user("func", role="employee")
    anonymous = Client()
    assert anonymous.get(reverse("users-list")).status_code == 403
    denied = login(student).get(reverse("users-list"))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert login(student).get(
        reverse("users-detail", args=[student.pk])
    ).status_code == (403)
    allowed = login(employee).get(reverse("users-list"))
    assert allowed.status_code == 200
    assert login(employee).get(
        reverse("users-detail", args=[student.pk])
    ).status_code == (200)


def test_writes_require_admin_and_csrf(admin_client):
    student = make_user("aluno")
    employee_client = login(make_user("func", role="employee"))
    assert post(employee_client, new_user_payload()).status_code == 403
    assert patch(employee_client, student.pk, {"name": "X"}).status_code == 403
    assert post(admin_client, new_user_payload(), csrf=False).status_code == 403
    assert patch(admin_client, student.pk, {"name": "X"}, csrf=False).status_code == (
        403
    )
    assert not User.objects.filter(username="bruno").exists()


def test_delete_is_not_allowed(admin_client):
    student = make_user("aluno")
    response = admin_client.delete(
        reverse("users-detail", args=[student.pk]),
        HTTP_X_CSRFTOKEN=admin_client.cookies["csrftoken"].value,
    )
    assert response.status_code == 405
    assert User.objects.filter(pk=student.pk).exists()


@pytest.mark.parametrize(
    ("role", "is_staff", "in_group"),
    [("admin", True, True), ("employee", True, False), ("student", False, False)],
)
def test_create_user_with_role(admin_client, role, is_staff, in_group):
    response = post(admin_client, new_user_payload(role=role))
    assert response.status_code == 201
    body = response.json()
    created = User.objects.get(username="bruno")
    assert body["id"] == created.pk
    assert body["name"] == "Bruno Lima"
    assert body["email"] == "bruno@udf.edu.br"
    assert body["role"] == role
    assert body["is_active"] is True
    assert "password" not in body
    assert set(body) == {
        "id",
        "username",
        "name",
        "email",
        "role",
        "is_active",
        "date_joined",
    }
    assert created.is_staff is is_staff
    assert created.groups.filter(name=ADMIN_GROUP).exists() is in_group
    assert (created.first_name, created.last_name) == ("Bruno", "Lima")
    assert created.check_password(PASSWORD)


def test_create_requires_email_and_valid_fields(admin_client):
    payload = new_user_payload()
    del payload["email"]
    response = post(admin_client, payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "email" in response.json()["error"]["details"]
    assert post(admin_client, new_user_payload(role="root")).status_code == 400
    assert post(admin_client, new_user_payload(username="a b")).status_code == 400
    assert post(admin_client, new_user_payload(extra=1)).status_code == 400


@pytest.mark.parametrize("weak", ["123", "12345678", "password", "bruno123"])
def test_weak_password_is_rejected(admin_client, weak):
    response = post(admin_client, new_user_payload(password=weak))
    assert response.status_code == 400
    assert "password" in response.json()["error"]["details"]
    assert not User.objects.filter(username="bruno").exists()


def test_patch_weak_password_is_rejected(admin_client):
    student = make_user("aluno")
    response = patch(admin_client, student.pk, {"password": "123"})
    assert response.status_code == 400
    student.refresh_from_db()
    assert student.check_password(PASSWORD)


def test_username_unique_case_insensitive(admin_client):
    make_user("Bruno")
    response = post(
        admin_client, new_user_payload(username="bruno", email="b2@udf.edu.br")
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_USERNAME"


def test_email_unique_case_insensitive(admin_client):
    other = make_user("carla", email="Carla@UDF.edu.br")
    response = post(admin_client, new_user_payload(email="carla@udf.edu.br"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_EMAIL"

    student = make_user("aluno", email="aluno@udf.edu.br")
    response = patch(admin_client, student.pk, {"email": "CARLA@udf.edu.br"})
    assert response.status_code == 409
    # Manter o próprio e-mail (mudando só a caixa) não é conflito.
    response = patch(admin_client, other.pk, {"email": "carla@udf.edu.br"})
    assert response.status_code == 200


def test_patch_updates_fields_and_role(admin_client):
    student = make_user("aluno", email="aluno@udf.edu.br")
    response = patch(
        admin_client,
        student.pk,
        {
            "name": "  Dora   Maria Souza ",
            "email": "dora@udf.edu.br",
            "role": "admin",
            "password": NEW_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Dora Maria Souza"
    assert response.json()["role"] == "admin"
    student.refresh_from_db()
    assert (student.first_name, student.last_name) == ("Dora", "Maria Souza")
    assert student.is_staff
    assert student.check_password(NEW_PASSWORD)

    response = patch(admin_client, student.pk, {"role": "employee"})
    assert response.json()["role"] == "employee"
    student.refresh_from_db()
    assert student.is_staff and not student.groups.filter(name=ADMIN_GROUP).exists()

    response = patch(admin_client, student.pk, {"role": "student", "is_active": False})
    assert response.json()["role"] == "student"
    assert response.json()["is_active"] is False
    student.refresh_from_db()
    assert not student.is_staff and not student.is_active


def test_admin_cannot_deactivate_or_demote_self(admin, admin_client):
    for payload in ({"is_active": False}, {"role": "employee"}, {"role": "student"}):
        response = patch(admin_client, admin.pk, payload)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
    admin.refresh_from_db()
    assert admin.is_active and get_role(admin) == "admin"
    # Outras alterações em si mesmo continuam permitidas.
    assert patch(admin_client, admin.pk, {"name": "Ana C."}).status_code == 200


def test_superuser_is_not_demoted(admin_client):
    root = make_user("raiz", superuser=True)
    response = patch(admin_client, root.pk, {"role": "student"})
    assert response.status_code == 400
    root.refresh_from_db()
    assert root.is_superuser and root.is_staff


def test_list_filters_order_and_pagination(admin, admin_client):
    make_user("zeca", first_name="Beatriz", email="bia@udf.edu.br")
    make_user("yuri", role="employee", first_name="Carlos")
    make_user("xavier", is_active=False)
    make_user("raiz", superuser=True)

    response = admin_client.get(reverse("users-list"))
    names = [user["name"] for user in response.json()]
    assert names == ["Ana Costa", "Beatriz", "Carlos", "raiz", "xavier"]

    def usernames(query):
        response = admin_client.get(reverse("users-list"), query)
        assert response.status_code == 200
        return [user["username"] for user in response.json()]

    assert usernames({"role": "admin"}) == ["chefe", "raiz"]
    assert usernames({"role": "employee"}) == ["yuri"]
    assert usernames({"role": "student"}) == ["zeca", "xavier"]
    assert usernames({"is_active": "false"}) == ["xavier"]
    assert usernames({"q": "BIA@"}) == ["zeca"]
    assert usernames({"limit": 2, "offset": 1}) == ["zeca", "yuri"]
    assert admin_client.get(reverse("users-list"), {"role": "x"}).status_code == 400
    assert admin_client.get(reverse("users-list"), {"foo": "1"}).status_code == 400


def test_detail_not_found(admin_client):
    response = admin_client.get(reverse("users-detail", args=[999999]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert admin_client.get("/api/v1/users/99999999999/").status_code == 404
