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
        ("labtech_local", "127.0.0.1", "56432"),
        ("labtech_ci", "127.0.0.1", "5432"),
    }
    target = (database["NAME"], database["HOST"], str(database["PORT"]))
    if target not in allowed_targets or database["TEST"]["NAME"] != (
        f"test_{database['NAME']}"
    ):
        raise RuntimeError("UC003 HTTP exige PostgreSQL local ou efêmero da CI.")

# Valores padrão dos campos descritivos (spaces.0003_campos).
DEFAULTS = {"name": "", "capacity": None, "location": "", "is_active": True}

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
        username="gestor", password="senha-forte-123", is_staff=True
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


@pytest.fixture
def regular_client():
    user = get_user_model().objects.create_user(
        username="comum", password="senha-forte-123"
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
    return client


def request_json(client, method, url, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return getattr(client, method)(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


@pytest.mark.parametrize(
    "method,detail", [("get", False), ("get", True), ("post", False), ("patch", True)]
)
def test_anonymous_requests_are_forbidden(method, detail):
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    url = (
        reverse("spaces-list")
        if not detail
        else reverse("spaces-detail", kwargs={"space_id": 1})
    )
    response = (
        client.get(url)
        if method == "get"
        else request_json(client, method, url, {"code": "LAB-01", "kind": "room"})
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_regular_user_can_read_but_cannot_write(regular_client):
    space = Space.objects.create(code="SALA-01", kind="room")
    detail_url = reverse("spaces-detail", kwargs={"space_id": space.pk})
    assert regular_client.get(reverse("spaces-list")).json() == [
        {"id": space.pk, "code": "SALA-01", "kind": "room", **DEFAULTS}
    ]
    assert regular_client.get(detail_url).json()["id"] == space.pk

    response = request_json(
        regular_client,
        "post",
        reverse("spaces-list"),
        {"code": "SALA-02", "kind": "room"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

    response = request_json(regular_client, "patch", detail_url, {"code": "SALA-02"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert list(Space.objects.values_list("code", flat=True)) == ["SALA-01"]


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
        **DEFAULTS,
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
    assert response.json() == {
        "id": space.pk,
        "code": "SALA-02",
        "kind": "room",
        **DEFAULTS,
    }
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
    assert response.json() == {
        "error": {
            "code": "DUPLICATE_CODE",
            "message": "Já existe um espaço com este código.",
        }
    }
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
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "details" in response.json()["error"]
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
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    space.refresh_from_db()
    assert (space.code, space.kind) == ("SALA-01", "room")


@pytest.mark.parametrize("space_id", [999999, 2**63])
def test_missing_space_returns_404_without_side_effects(logged_in_client, space_id):
    url = reverse("spaces-detail", kwargs={"space_id": space_id})
    assert logged_in_client.get(url).status_code == 404
    assert logged_in_client.get(url).json()["error"]["code"] == "NOT_FOUND"
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


def test_new_fields_are_created_patched_and_read(logged_in_client, regular_client):
    list_url = reverse("spaces-list")
    created = request_json(
        logged_in_client,
        "post",
        list_url,
        {
            "code": "LAB-10",
            "kind": "laboratory",
            "name": "  Laboratório de Redes ",
            "capacity": 30,
            "location": "Bloco B, 2º andar",
        },
    )
    assert created.status_code == 201
    space_id = created.json()["id"]
    assert created.json() == {
        "id": space_id,
        "code": "LAB-10",
        "kind": "laboratory",
        "name": "Laboratório de Redes",
        "capacity": 30,
        "location": "Bloco B, 2º andar",
        "is_active": True,
    }
    url = reverse("spaces-detail", kwargs={"space_id": space_id})
    patched = request_json(
        logged_in_client,
        "patch",
        url,
        {"capacity": None, "is_active": False, "name": ""},
    )
    assert patched.status_code == 200
    assert patched.json() == {
        **created.json(),
        "capacity": None,
        "is_active": False,
        "name": "",
    }
    space = Space.objects.get(pk=space_id)
    assert (space.capacity, space.is_active, space.name) == (None, False, "")
    assert regular_client.get(url).json() == patched.json()
    response = request_json(regular_client, "patch", url, {"is_active": True})
    assert response.status_code == 403
    assert Space.objects.get(pk=space_id).is_active is False


def test_list_filters_by_is_active_and_kind(regular_client):
    lab = Space.objects.create(code="LAB-01", kind="laboratory")
    room = Space.objects.create(code="SALA-01", kind="room")
    old_room = Space.objects.create(code="SALA-02", kind="room", is_active=False)

    def ids(query):
        response = regular_client.get(reverse("spaces-list") + query)
        assert response.status_code == 200
        return [item["id"] for item in response.json()]

    assert ids("") == [lab.pk, room.pk, old_room.pk]
    assert ids("?is_active=true") == [lab.pk, room.pk]
    assert ids("?is_active=false") == [old_room.pk]
    assert ids("?kind=room") == [room.pk, old_room.pk]
    assert ids("?kind=room&is_active=true") == [room.pk]


@pytest.mark.parametrize(
    "query", ["?is_active=1", "?kind=other", "?kind=room&kind=laboratory", "?x=1"]
)
def test_invalid_list_filters_return_400(regular_client, query):
    response = regular_client.get(reverse("spaces-list") + query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    "payload",
    [
        {"capacity": 0},
        {"capacity": -1},
        {"capacity": "10"},
        {"capacity": True},
        {"capacity": 1.5},
        {"is_active": "false"},
        {"is_active": 0},
        {"name": "A" * 121},
        {"location": "A" * 121},
    ],
)
def test_invalid_new_fields_return_400(logged_in_client, payload):
    response = request_json(
        logged_in_client,
        "post",
        reverse("spaces-list"),
        {"code": "LAB-01", "kind": "laboratory", **payload},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert Space.objects.count() == 0


def test_database_rejects_non_positive_capacity():
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Space.objects.create(code="LAB-01", kind="room", capacity=0)
    assert (
        error.value.__cause__.diag.constraint_name == "spaces_space_capacity_positive"
    )
