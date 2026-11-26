"""Fluxo integrado do MVP com sessões reais e PostgreSQL de teste isolado."""

import json
from urllib.parse import urlencode

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import resolve, reverse

from apps.bookings.models import Booking
from apps.keys.models import Key, KeyLoan, KeyMovement
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
        raise RuntimeError("O teste integrado exige PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="O fluxo integrado exige PostgreSQL local ou da CI",
    ),
]

PASSWORD = "senha-forte-123"
START = "2026-11-20T10:00:00-03:00"
END = "2026-11-20T11:00:00-03:00"


def login_client(user):
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    assert "sessionid" not in client.cookies
    response = client.post(
        reverse("auth-login"),
        data=json.dumps({"identifier": user.username, "password": PASSWORD}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200
    assert response.json() == {"user": {"id": user.pk}}
    session = Session.objects.get(session_key=client.cookies["sessionid"].value)
    assert session.get_decoded()["_auth_user_id"] == str(user.pk)
    me = client.get(reverse("auth-me")).json()
    assert {key: me[key] for key in ("id", "is_staff")} == {
        "id": user.pk,
        "is_staff": user.is_staff,
    }
    return client


def write_json(client, method, url, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return getattr(client, method)(
        url, data=json.dumps(payload), content_type="application/json", **headers
    )


def error_code(response, status_code, code):
    assert response.status_code == status_code
    error = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    return error


def test_mvp_end_to_end_with_real_sessions_and_csrf():
    staff_user = get_user_model().objects.create_user(
        username="mvp_staff", password=PASSWORD, is_staff=True
    )
    regular_user = get_user_model().objects.create_user(
        username="mvp_regular", password=PASSWORD
    )
    staff = login_client(staff_user)
    regular = login_client(regular_user)

    assert staff.get(reverse("api-health")).json() == {
        "status": "ok",
        "service": "labtech-api",
    }
    space_list_url = reverse("spaces-list")
    assert regular.get(space_list_url).json() == []
    missing_csrf = write_json(
        staff,
        "post",
        space_list_url,
        {"code": "LAB-MVP", "kind": "laboratory"},
        csrf=False,
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json() == {"error": "CSRF inválido ou ausente."}

    created_space = write_json(
        staff, "post", space_list_url, {"code": " LAB-MVP ", "kind": "laboratory"}
    )
    assert created_space.status_code == 201
    space_id = created_space.json()["id"]
    assert created_space.json() == {
        "id": space_id,
        "code": "LAB-MVP",
        "kind": "laboratory",
        "name": "",
        "capacity": None,
        "location": "",
        "is_active": True,
    }
    assert Space.objects.get(pk=space_id).code == "LAB-MVP"
    space_detail_url = reverse("spaces-detail", args=[space_id])
    assert regular.get(space_list_url).json() == [created_space.json()]
    assert regular.get(space_detail_url).json() == created_space.json()
    assert (
        write_json(staff, "patch", space_detail_url, {"kind": "laboratory"}).status_code
        == 200
    )

    error_code(
        write_json(
            regular,
            "post",
            space_list_url,
            {"code": "LAB-NEGADO", "kind": "laboratory"},
        ),
        403,
        "FORBIDDEN",
    )
    error_code(
        write_json(regular, "patch", space_detail_url, {"code": "LAB-NEGADO"}),
        403,
        "FORBIDDEN",
    )
    assert Space.objects.count() == 1
    error_code(regular.get(reverse("spaces-detail", args=[999999])), 404, "NOT_FOUND")
    invalid_request = error_code(
        write_json(staff, "post", space_list_url, {"kind": "room"}),
        400,
        "INVALID_REQUEST",
    )
    assert "code" in invalid_request["details"]

    booking_list_url = reverse("bookings-list")
    booking_payload = {"space_id": space_id, "start_at": START, "end_at": END}
    error_code(
        write_json(regular, "post", booking_list_url, booking_payload), 403, "FORBIDDEN"
    )
    created_booking = write_json(staff, "post", booking_list_url, booking_payload)
    assert created_booking.status_code == 201
    booking = created_booking.json()
    booking_id = booking["id"]
    assert set(booking) == {
        "id",
        "space_id",
        "start_at",
        "end_at",
        "status",
        "created_at",
        "cancelled_at",
    }
    assert (booking["space_id"], booking["status"], booking["cancelled_at"]) == (
        space_id,
        "active",
        None,
    )
    assert Booking.objects.get(pk=booking_id).user_id == staff_user.pk
    error_code(regular.get(booking_list_url), 403, "FORBIDDEN")
    error_code(
        regular.get(reverse("bookings-detail", args=[booking_id])), 403, "FORBIDDEN"
    )
    assert staff.get(booking_list_url).json() == [booking]
    assert staff.get(reverse("bookings-detail", args=[booking_id])).json() == booking

    conflict = write_json(staff, "post", booking_list_url, booking_payload)
    assert error_code(conflict, 409, "BOOKING_CONFLICT")["details"] == {
        "space_id": space_id
    }
    assert Booking.objects.count() == 1
    window = urlencode({"start_at": START, "end_at": END})
    availability_url = reverse("booking-availability", args=[space_id]) + "?" + window
    agenda_url = reverse("booking-agenda", args=[space_id]) + "?" + window
    assert regular.get(availability_url).json() == {
        "space_id": space_id,
        "start_at": booking["start_at"],
        "end_at": booking["end_at"],
        "available": False,
    }
    assert regular.get(agenda_url).json() == {
        "space_id": space_id,
        "start_at": booking["start_at"],
        "end_at": booking["end_at"],
        "occupied": [{"start_at": booking["start_at"], "end_at": booking["end_at"]}],
    }

    error_code(
        write_json(regular, "post", reverse("bookings-cancel", args=[booking_id]), {}),
        403,
        "FORBIDDEN",
    )
    cancelled = write_json(
        staff, "post", reverse("bookings-cancel", args=[booking_id]), {}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["id"] == booking_id
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancelled_at"]
    assert regular.get(availability_url).json()["available"] is True
    assert regular.get(agenda_url).json()["occupied"] == []

    keys_url = reverse("keys-list")
    key_payload = {"space_id": space_id, "label": "LAB-MVP-01"}
    error_code(write_json(regular, "post", keys_url, key_payload), 403, "FORBIDDEN")
    created_key = write_json(staff, "post", keys_url, key_payload)
    assert created_key.status_code == 201
    key = Key.objects.get(pk=created_key.json()["id"])
    assert (key.space_id, key.label, key.status) == (
        space_id,
        "LAB-MVP-01",
        "available",
    )
    checkout_url = reverse("key-loans-checkout")
    checkout_payload = {"key_id": key.pk, "responsible_user_id": regular_user.pk}
    error_code(
        write_json(regular, "post", checkout_url, checkout_payload), 403, "FORBIDDEN"
    )
    assert KeyLoan.objects.count() == 0
    checkout = write_json(staff, "post", checkout_url, checkout_payload)
    assert checkout.status_code == 201
    loan = checkout.json()
    assert set(loan) == {
        "id",
        "key_id",
        "key_label",
        "space_id",
        "space_code",
        "responsible_user_id",
        "responsible_name",
        "checkout_operator_id",
        "checked_out_at",
        "returned_at",
        "return_operator_id",
        "status",
    }
    assert (loan["key_id"], loan["responsible_user_id"], loan["status"]) == (
        key.pk,
        regular_user.pk,
        "active",
    )
    assert KeyLoan.objects.get(pk=loan["id"]).checkout_operator_id == staff_user.pk
    key_availability_url = reverse("key-loan-availability", args=[key.pk])
    movements_url = reverse("key-movements", args=[key.pk])
    error_code(regular.get(key_availability_url), 403, "FORBIDDEN")
    assert staff.get(key_availability_url).json() == {
        "key_id": key.pk,
        "has_active_loan": True,
    }
    assert error_code(
        write_json(staff, "post", checkout_url, checkout_payload),
        409,
        "KEY_UNAVAILABLE",
    )["details"] == {"key_id": key.pk}

    return_url = reverse("key-loans-return", args=[loan["id"]])
    error_code(write_json(regular, "post", return_url, {}), 403, "FORBIDDEN")
    assert KeyLoan.objects.get(pk=loan["id"]).returned_at is None
    returned = write_json(staff, "post", return_url, {})
    assert returned.status_code == 200
    assert returned.json()["id"] == loan["id"]
    assert returned.json()["status"] == "returned"
    assert returned.json()["returned_at"]
    error_code(regular.get(key_availability_url), 403, "FORBIDDEN")
    error_code(regular.get(movements_url), 403, "FORBIDDEN")
    assert staff.get(key_availability_url).json()["has_active_loan"] is False
    history = staff.get(movements_url)
    assert history.status_code == 200
    assert history.json()["key_id"] == key.pk
    events = history.json()["events"]
    assert [(event["type"], event["loan_id"]) for event in events] == [
        ("checkout", loan["id"]),
        ("return", loan["id"]),
    ]
    assert all(event["occurred_at"] for event in events)
    assert KeyMovement.objects.filter(loan_id=loan["id"]).count() == 2

    logout = write_json(regular, "post", reverse("auth-logout"), {})
    assert logout.status_code == 200
    assert logout.json() == {"status": "signed_out"}
    error_code(regular.get(space_list_url), 403, "FORBIDDEN")


def test_integrated_routes_resolve_without_collisions():
    routes = {
        "api-health": (),
        "auth-csrf": (),
        "auth-login": (),
        "auth-logout": (),
        "auth-me": (),
        "users-list": (),
        "users-detail": (1,),
        "spaces-list": (),
        "spaces-detail": (1,),
        "bookings-list": (),
        "bookings-detail": (1,),
        "bookings-cancel": (1,),
        "booking-availability": (1,),
        "booking-agenda": (1,),
        "key-loans-checkout": (),
        "key-loans-return": (1,),
        "key-loan-availability": (1,),
        "key-movements": (1,),
    }
    paths = [reverse(name, args=args) for name, args in routes.items()]
    assert len(paths) == len(set(paths))
    for name, args in routes.items():
        assert resolve(reverse(name, args=args)).url_name == name
