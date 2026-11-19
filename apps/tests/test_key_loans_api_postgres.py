"""UC005–UC008 com sessões reais e PostgreSQL de teste isolado."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.keys.models import Key, KeyLoan, KeyMovement
from apps.keys.services import checkout_key, return_key
from apps.spaces.models import Space

database = settings.DATABASES["default"]
if database["ENGINE"] == "django.db.backends.postgresql":
    allowed = {
        ("labtech_local", "127.0.0.1", "55432"),
        ("labtech_ci", "127.0.0.1", "5432"),
    }
    target = (database["NAME"], database["HOST"], str(database["PORT"]))
    if target not in allowed or database["TEST"]["NAME"] != f"test_{database['NAME']}":
        raise RuntimeError("UC005–UC008 exigem PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC005–UC008 exigem PostgreSQL local ou da CI",
    ),
]

AT = datetime(2026, 10, 30, 10, tzinfo=UTC)


@pytest.fixture
def actors():
    user_model = get_user_model()
    assert user_model._meta.label == "auth.User"
    staff = user_model.objects.create_user(
        username="operador", password="senha-forte-123", is_staff=True
    )
    responsible = user_model.objects.create_user(
        username="responsavel", password="senha-forte-456"
    )
    ordinary = user_model.objects.create_user(
        username="comum", password="senha-forte-789"
    )
    space = Space.objects.create(code="SALA-API", kind="room")
    key = Key.objects.create(space=space)
    return key, staff, responsible, ordinary


def login_client(user, *, raise_request_exception=True):
    client = Client(
        enforce_csrf_checks=True, raise_request_exception=raise_request_exception
    )
    assert client.get(reverse("auth-csrf")).status_code == 204
    response = client.post(
        reverse("auth-login"),
        {"identifier": user.username, "password": "senha-forte-123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200
    assert "sessionid" in client.cookies
    return client


def post_json(client, url, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return client.post(url, payload, content_type="application/json", **headers)


def urls(key, loan_id=1):
    return (
        reverse("key-loans-checkout"),
        reverse("key-loans-return", args=[loan_id]),
        reverse("key-loan-availability", args=[key.pk]),
        reverse("key-movements", args=[key.pk]),
    )


def test_checkout_return_availability_and_history(actors):
    key, staff, responsible, _ = actors
    client = login_client(staff)
    checkout_url, _, availability_url, movements_url = urls(key)
    assert client.get(availability_url).json() == {
        "key_id": key.pk,
        "has_active_loan": False,
    }
    assert client.get(movements_url).json() == {"key_id": key.pk, "events": []}

    before = timezone.now()
    checkout = post_json(
        client,
        checkout_url,
        {"key_id": key.pk, "responsible_user_id": responsible.pk},
    )
    after = timezone.now()
    assert checkout.status_code == 201
    data = checkout.json()
    assert set(data) == {
        "id",
        "key_id",
        "responsible_user_id",
        "checked_out_at",
        "status",
    }
    assert (data["key_id"], data["responsible_user_id"], data["status"]) == (
        key.pk,
        responsible.pk,
        "active",
    )
    assert before <= datetime.fromisoformat(data["checked_out_at"]) <= after
    loan = KeyLoan.objects.get(pk=data["id"])
    assert loan.checkout_operator_id == staff.pk
    assert loan.checked_out_at == datetime.fromisoformat(data["checked_out_at"])
    assert client.get(availability_url).json()["has_active_loan"] is True

    duplicate = post_json(
        client,
        checkout_url,
        {"key_id": key.pk, "responsible_user_id": responsible.pk},
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "error": {
            "code": "KEY_UNAVAILABLE",
            "message": "Chave com empréstimo ativo.",
            "details": {"key_id": key.pk},
        }
    }
    assert KeyLoan.objects.count() == 1
    assert KeyMovement.objects.count() == 1

    return_url = reverse("key-loans-return", args=[loan.pk])
    assert post_json(client, return_url, {}, csrf=False).status_code == 403
    assert KeyLoan.objects.get(pk=loan.pk).returned_at is None
    before_return = timezone.now()
    returned = post_json(client, return_url, {})
    after_return = timezone.now()
    assert returned.status_code == 200
    assert returned.json()["id"] == loan.pk
    assert returned.json()["status"] == "returned"
    returned_at = datetime.fromisoformat(returned.json()["returned_at"])
    assert before_return <= returned_at <= after_return
    loan.refresh_from_db()
    assert loan.return_operator_id == staff.pk
    assert loan.returned_at == returned_at
    assert client.get(availability_url).json()["has_active_loan"] is False

    events = client.get(movements_url).json()["events"]
    assert events == [
        {"type": "checkout", "loan_id": loan.pk, "occurred_at": data["checked_out_at"]},
        {
            "type": "return",
            "loan_id": loan.pk,
            "occurred_at": returned.json()["returned_at"],
        },
    ]
    assert all(set(event) == {"type", "loan_id", "occurred_at"} for event in events)

    repeated = post_json(client, return_url, {})
    assert repeated.status_code == 409
    assert repeated.json() == {
        "error": {
            "code": "LOAN_ALREADY_RETURNED",
            "message": "Empréstimo já encerrado.",
        }
    }
    assert client.get(movements_url).json()["events"] == events
    assert KeyMovement.objects.count() == 2


def test_authentication_staff_permission_and_csrf(actors):
    key, staff, responsible, ordinary = actors
    checkout_url, return_url, availability_url, movements_url = urls(key)
    anonymous = Client(enforce_csrf_checks=True)
    assert anonymous.get(availability_url).status_code == 403
    assert anonymous.get(movements_url).status_code == 403
    assert (
        post_json(
            anonymous,
            checkout_url,
            {"key_id": key.pk, "responsible_user_id": responsible.pk},
            csrf=False,
        ).status_code
        == 403
    )
    assert anonymous.get(reverse("auth-csrf")).status_code == 204
    assert (
        post_json(
            anonymous,
            checkout_url,
            {"key_id": key.pk, "responsible_user_id": responsible.pk},
        ).json()["error"]["code"]
        == "FORBIDDEN"
    )

    ordinary_client = Client(enforce_csrf_checks=True)
    assert ordinary_client.login(username=ordinary.username, password="senha-forte-789")
    assert ordinary_client.get(reverse("auth-csrf")).status_code == 204
    assert ordinary_client.get(availability_url).status_code == 200
    assert ordinary_client.get(movements_url).status_code == 200
    for url, payload in (
        (checkout_url, {"key_id": key.pk, "responsible_user_id": responsible.pk}),
        (return_url, {}),
    ):
        response = post_json(ordinary_client, url, payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    staff_client = login_client(staff)
    assert (
        post_json(
            staff_client,
            checkout_url,
            {"key_id": key.pk, "responsible_user_id": responsible.pk},
            csrf=False,
        ).status_code
        == 403
    )
    assert KeyLoan.objects.count() == 0
    assert KeyMovement.objects.count() == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"key_id": 1},
        {"key_id": "1", "responsible_user_id": 1},
        {"key_id": True, "responsible_user_id": 1},
        {"key_id": 1, "responsible_user_id": 1.5},
        {"key_id": 0, "responsible_user_id": 1},
        {"key_id": 1, "responsible_user_id": 1, "operator_id": 2},
        {"key_id": 1, "responsible_user_id": 1, "checked_out_at": AT.isoformat()},
        [1, 2],
    ],
)
def test_checkout_rejects_invalid_payload_without_writes(actors, payload):
    _, staff, _, _ = actors
    client = login_client(staff)
    response = post_json(client, reverse("key-loans-checkout"), payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert not KeyLoan.objects.exists()
    assert not KeyMovement.objects.exists()


def test_malformed_json_returns_400_without_writes(actors):
    _, staff, _, _ = actors
    client = login_client(staff)
    response = client.post(
        reverse("key-loans-checkout"),
        data="{",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert not KeyLoan.objects.exists()


def test_missing_resources_and_invalid_return_body_have_no_effects(actors):
    key, staff, responsible, _ = actors
    client = login_client(staff)
    checkout_url, _, _, _ = urls(key)
    missing_key = post_json(
        client,
        checkout_url,
        {"key_id": key.pk + 9999, "responsible_user_id": responsible.pk},
    )
    missing_responsible = post_json(
        client,
        checkout_url,
        {"key_id": key.pk, "responsible_user_id": responsible.pk + 9999},
    )
    for response in (missing_key, missing_responsible):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    for name in ("key-loan-availability", "key-movements"):
        response = client.get(reverse(name, args=[key.pk + 9999]))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    loan = checkout_key(key_id=key.pk, responsible=responsible, operator=staff)
    return_url = reverse("key-loans-return", args=[loan.pk])
    for payload in ({"returned_at": AT.isoformat()}, [], {"operator_id": staff.pk}):
        response = post_json(client, return_url, payload)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
    missing_loan = post_json(
        client, reverse("key-loans-return", args=[loan.pk + 9999]), {}
    )
    assert missing_loan.status_code == 404
    assert missing_loan.json()["error"]["code"] == "NOT_FOUND"
    loan.refresh_from_db()
    assert loan.returned_at is None
    assert list(KeyMovement.objects.values_list("kind", flat=True)) == ["checkout"]


def test_history_uses_time_then_id_order_and_exposes_no_personal_data(actors):
    key, staff, responsible, _ = actors
    first = checkout_key(
        key_id=key.pk, responsible=responsible, operator=staff, occurred_at=AT
    )
    return_key(loan_id=first.pk, operator=staff, occurred_at=AT)
    second = checkout_key(
        key_id=key.pk, responsible=responsible, operator=staff, occurred_at=AT
    )
    client = login_client(staff)
    response = client.get(reverse("key-movements", args=[key.pk]))
    assert response.status_code == 200
    events = response.json()["events"]
    assert [(event["type"], event["loan_id"]) for event in events] == [
        ("checkout", first.pk),
        ("return", first.pk),
        ("checkout", second.pk),
    ]
    assert all(set(event) == {"type", "loan_id", "occurred_at"} for event in events)
    assert len({event["occurred_at"] for event in events}) == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_http_checkouts_leave_one_loan(actors):
    key, staff, responsible, _ = actors
    clients = [login_client(staff), login_client(staff)]
    gate = Barrier(2, timeout=10)
    url = reverse("key-loans-checkout")
    payload = {"key_id": key.pk, "responsible_user_id": responsible.pk}

    def attempt(client):
        try:
            gate.wait()
            response = post_json(client, url, payload)
            return response.status_code, response.json()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, clients))
    assert sorted(status for status, _ in outcomes) == [201, 409]
    assert next(body for status, body in outcomes if status == 409)["error"][
        "code"
    ] == ("KEY_UNAVAILABLE")
    assert KeyLoan.objects.filter(key=key).count() == 1
    assert KeyMovement.objects.filter(loan__key=key).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_http_returns_preserve_one_return_event(actors):
    key, staff, responsible, _ = actors
    loan = checkout_key(key_id=key.pk, responsible=responsible, operator=staff)
    clients = [login_client(staff), login_client(staff)]
    gate = Barrier(2, timeout=10)
    url = reverse("key-loans-return", args=[loan.pk])

    def attempt(client):
        try:
            gate.wait()
            response = post_json(client, url, {})
            return response.status_code, response.json()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, clients))
    assert sorted(status for status, _ in outcomes) == [200, 409]
    assert (
        next(body for status, body in outcomes if status == 409)["error"]["code"]
        == "LOAN_ALREADY_RETURNED"
    )
    loan.refresh_from_db()
    assert loan.returned_at is not None
    assert list(
        KeyMovement.objects.filter(loan=loan)
        .order_by("id")
        .values_list("kind", flat=True)
    ) == [
        "checkout",
        "return",
    ]


def test_http_checkout_rolls_back_on_unexpected_movement_error(actors, monkeypatch):
    key, staff, responsible, _ = actors
    client = login_client(staff, raise_request_exception=False)

    def fail(*args, **kwargs):
        raise IntegrityError("falha inesperada")

    monkeypatch.setattr(KeyMovement.objects, "create", fail)
    response = post_json(
        client,
        reverse("key-loans-checkout"),
        {"key_id": key.pk, "responsible_user_id": responsible.pk},
    )
    assert response.status_code == 500
    assert not KeyLoan.objects.exists()
    assert not KeyMovement.objects.exists()


def test_http_return_rolls_back_on_unexpected_movement_error(actors, monkeypatch):
    key, staff, responsible, _ = actors
    loan = checkout_key(key_id=key.pk, responsible=responsible, operator=staff)
    client = login_client(staff, raise_request_exception=False)

    def fail(*args, **kwargs):
        raise IntegrityError("falha inesperada")

    monkeypatch.setattr(KeyMovement.objects, "create", fail)
    response = post_json(client, reverse("key-loans-return", args=[loan.pk]), {})
    assert response.status_code == 500
    loan.refresh_from_db()
    assert loan.returned_at is None
    assert loan.return_operator_id is None
    assert list(KeyMovement.objects.values_list("kind", flat=True)) == ["checkout"]


def test_unexpected_value_error_is_not_a_business_conflict(actors, monkeypatch):
    key, staff, responsible, _ = actors
    client = login_client(staff, raise_request_exception=False)

    def fail(*args, **kwargs):
        raise ValueError("histórico inconsistente")

    monkeypatch.setattr("apps.keys.loan_views.checkout_key", fail)
    response = post_json(
        client,
        reverse("key-loans-checkout"),
        {"key_id": key.pk, "responsible_user_id": responsible.pk},
    )
    assert response.status_code == 500
    assert not KeyLoan.objects.exists()


def test_history_endpoints_are_read_only(actors):
    key, staff, _, _ = actors
    client = login_client(staff)
    for name in ("key-loan-availability", "key-movements"):
        response = post_json(client, reverse(name, args=[key.pk]), {})
        assert response.status_code == 405
    assert not KeyMovement.objects.exists()
