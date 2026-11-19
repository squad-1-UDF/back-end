"""UC003 via HTTP, sessão Django e PostgreSQL de teste isolado."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.spaces.api import is_duplicate_code
from apps.spaces.models import Space

database = settings.DATABASES["default"]
if database["ENGINE"] == "django.db.backends.postgresql":
    allowed_targets = {
        ("labtech_local", "127.0.0.1", "55432"),
        ("labtech_ci", "127.0.0.1", "5432"),
    }
    target = (database["NAME"], database["HOST"], str(database["PORT"]))
    if target not in allowed_targets or database["TEST"]["NAME"] != (
        f"test_{database['NAME']}"
    ):
        raise RuntimeError("UC003 HTTP exige PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC003 HTTP exige PostgreSQL local ou da CI",
    ),
]


@pytest.fixture
def logged_in_client():
    user = get_user_model().objects.create_user(
        username="gestor", password="senha-forte-123"
    )
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    login = client.post(
        reverse("auth-login"),
        data=json.dumps({"identifier": user.username, "password": "senha-forte-123"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert login.status_code == 200
    assert Session.objects.filter(
        session_key=client.cookies["sessionid"].value
    ).exists()
    return client


def request_json(client, method, url, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return getattr(client, method)(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


@pytest.mark.parametrize("method", ["get", "post", "patch"])
def test_anonymous_requests_are_forbidden(method):
    client = Client(enforce_csrf_checks=True)
    url = (
        reverse("spaces-list")
        if method != "patch"
        else reverse("spaces-detail", kwargs={"space_id": 1})
    )
    response = (
        client.get(url)
        if method == "get"
        else request_json(
            client, method, url, {"code": "LAB-01", "kind": "room"}, csrf=False
        )
    )
    assert response.status_code == 403


def test_empty_list_create_and_read_in_later_request(logged_in_client):
    client = logged_in_client
    list_url = reverse("spaces-list")
    assert client.get(list_url).json() == []

    laboratory = request_json(
        client, "post", list_url, {"code": " LAB-02 ", "kind": "laboratory"}
    )
    room = request_json(client, "post", list_url, {"code": "SALA-01", "kind": "room"})
    assert laboratory.status_code == room.status_code == 201
    assert laboratory.json() == {
        "id": laboratory.json()["id"],
        "code": "LAB-02",
        "kind": "laboratory",
    }
    assert room.json()["code"] == "SALA-01"
    assert isinstance(laboratory.json()["id"], int)
    assert laboratory.json()["id"] < room.json()["id"]

    later_client = Client(enforce_csrf_checks=True)
    later_client.cookies["sessionid"] = client.cookies["sessionid"].value
    assert later_client.get(list_url).json() == [laboratory.json(), room.json()]
    detail_url = reverse("spaces-detail", kwargs={"space_id": laboratory.json()["id"]})
    assert later_client.get(detail_url).json() == laboratory.json()
    assert Space.objects.get(pk=laboratory.json()["id"]).code == "LAB-02"


def test_patch_is_partial_and_persists(logged_in_client):
    space = Space.objects.create(code="SALA-01", kind="room")
    url = reverse("spaces-detail", kwargs={"space_id": space.pk})
    response = request_json(logged_in_client, "patch", url, {"code": " SALA-02 "})
    assert response.status_code == 200
    assert response.json() == {"id": space.pk, "code": "SALA-02", "kind": "room"}
    assert logged_in_client.get(url).json() == response.json()
    space.refresh_from_db()
    assert (space.code, space.kind) == ("SALA-02", "room")

    response = request_json(logged_in_client, "patch", url, {"kind": "laboratory"})
    assert response.status_code == 200
    space.refresh_from_db()
    assert (space.code, space.kind) == ("SALA-02", "laboratory")


def test_duplicate_code_returns_409_without_side_effects(logged_in_client):
    first = Space.objects.create(code="LAB-01", kind="laboratory")
    second = Space.objects.create(code="LAB-02", kind="room")
    response = request_json(
        logged_in_client,
        "post",
        reverse("spaces-list"),
        {"code": " LAB-01 ", "kind": "room"},
    )
    assert response.status_code == 409
    assert "code" in response.json()
    assert Space.objects.count() == 2

    response = request_json(
        logged_in_client,
        "patch",
        reverse("spaces-detail", kwargs={"space_id": second.pk}),
        {"code": first.code, "kind": "laboratory"},
    )
    assert response.status_code == 409
    second.refresh_from_db()
    assert (second.code, second.kind) == ("LAB-02", "room")
    assert Space.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_posts_return_201_and_409(logged_in_client):
    gate = Barrier(2, timeout=10)

    def create_space():
        client = Client(enforce_csrf_checks=True)
        client.cookies["sessionid"] = logged_in_client.cookies["sessionid"].value
        client.cookies["csrftoken"] = logged_in_client.cookies["csrftoken"].value
        try:
            gate.wait()
            return request_json(
                client,
                "post",
                reverse("spaces-list"),
                {"code": "LAB-CONCORRENTE", "kind": "laboratory"},
            ).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: create_space(), range(2)))

    assert sorted(responses) == [201, 409]
    assert Space.objects.filter(code="LAB-CONCORRENTE").count() == 1


def test_other_database_constraint_is_not_classified_as_duplicate_code():
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Space.objects.create(code=" ", kind="room")
    assert not is_duplicate_code(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "", "kind": "room"},
        {"code": "   ", "kind": "room"},
        {"code": "A" * 51, "kind": "room"},
        {"code": "SALA-01", "kind": "other"},
        {"kind": "room"},
    ],
)
def test_invalid_post_returns_400_without_side_effects(logged_in_client, payload):
    response = request_json(logged_in_client, "post", reverse("spaces-list"), payload)
    assert response.status_code == 400
    assert Space.objects.count() == 0


@pytest.mark.parametrize(
    "payload", [{"code": " "}, {"kind": "other"}, {"code": "A" * 51}]
)
def test_invalid_patch_returns_400_without_side_effects(logged_in_client, payload):
    space = Space.objects.create(code="SALA-01", kind="room")
    response = request_json(
        logged_in_client,
        "patch",
        reverse("spaces-detail", kwargs={"space_id": space.pk}),
        payload,
    )
    assert response.status_code == 400
    space.refresh_from_db()
    assert (space.code, space.kind) == ("SALA-01", "room")


@pytest.mark.parametrize("space_id", [999999, 2**63])
def test_missing_space_returns_404_without_side_effects(logged_in_client, space_id):
    url = reverse("spaces-detail", kwargs={"space_id": space_id})
    assert logged_in_client.get(url).status_code == 404
    response = request_json(logged_in_client, "patch", url, {"code": "SALA-01"})
    assert response.status_code == 404
    assert Space.objects.count() == 0


def test_post_and_patch_require_csrf_with_real_session(logged_in_client):
    client = logged_in_client
    url = reverse("spaces-list")
    response = request_json(
        client, "post", url, {"code": "SALA-01", "kind": "room"}, csrf=False
    )
    assert response.status_code == 403
    assert Space.objects.count() == 0

    response = request_json(client, "post", url, {"code": "SALA-01", "kind": "room"})
    assert response.status_code == 201
    space_id = response.json()["id"]
    detail_url = reverse("spaces-detail", kwargs={"space_id": space_id})
    response = request_json(
        client, "patch", detail_url, {"kind": "laboratory"}, csrf=False
    )
    assert response.status_code == 403
    assert Space.objects.get(pk=space_id).kind == "room"

    response = request_json(client, "patch", detail_url, {"kind": "laboratory"})
    assert response.status_code == 200
    assert Space.objects.get(pk=response.json()["id"]).kind == "laboratory"
