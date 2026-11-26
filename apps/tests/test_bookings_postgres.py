"""Reservas HTTP e constraints no PostgreSQL de teste isolado."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from urllib.parse import urlencode

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import create_booking
from apps.spaces.models import Space

database = settings.DATABASES["default"]
if database["ENGINE"] == "django.db.backends.postgresql":
    allowed = {
        ("labtech_local", "127.0.0.1", "55432"),
        ("labtech_local", "127.0.0.1", "56432"),
        ("labtech_ci", "127.0.0.1", "5432"),
    }
    target = (database["NAME"], database["HOST"], str(database["PORT"]))
    if target not in allowed or database["TEST"]["NAME"] != f"test_{database['NAME']}":
        raise RuntimeError("Reservas exigem PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="Reservas exigem PostgreSQL local ou da CI",
    ),
]

START = datetime(2026, 11, 20, 13, tzinfo=UTC)
END = START + timedelta(hours=1)
PASSWORD = "senha-forte-123"


@pytest.fixture
def domain():
    user_model = get_user_model()
    assert user_model._meta.label == "auth.User"
    owner = user_model.objects.create_user(username="titular", password=PASSWORD)
    other = user_model.objects.create_user(username="outro", password=PASSWORD)
    staff = user_model.objects.create_user(
        username="gestor", password=PASSWORD, is_staff=True
    )
    room = Space.objects.create(code="SALA-RESERVA", kind="room")
    lab = Space.objects.create(code="LAB-RESERVA", kind="laboratory")
    return room, lab, owner, other, staff


def client_for(user, *, raise_request_exception=True):
    client = Client(
        enforce_csrf_checks=True, raise_request_exception=raise_request_exception
    )
    assert client.login(username=user.username, password=PASSWORD)
    assert client.get(reverse("auth-csrf")).status_code == 204
    return client


def post_json(client, url, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return client.post(url, payload, content_type="application/json", **headers)


def payload(space, *, start=START, end=END):
    return {
        "space_id": space.pk,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
    }


def window_url(name, space, *, start=START, end=END):
    return (
        reverse(name, args=[space.pk])
        + "?"
        + urlencode({"start_at": start.isoformat(), "end_at": end.isoformat()})
    )


def test_migration_installs_partial_half_open_exclusion_constraint():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = %s)",
            ["btree_gist"],
        )
        assert cursor.fetchone()[0]
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
            ["bookings_active_no_overlap"],
        )
        definition = cursor.fetchone()[0]
    assert "EXCLUDE USING gist" in definition
    assert "tstzrange" in definition.lower()
    assert "[)" in definition
    assert "status" in definition and "active" in definition


def test_database_rejects_direct_overlap_and_allows_adjacent_or_other_space(domain):
    room, lab, owner, _, _ = domain
    first = create_booking(space=room, user=owner, start_at=START, end_at=END)
    assert first.status == Booking.Status.ACTIVE
    assert first.created_at is not None
    for start, end in (
        (START, END),
        (START + timedelta(minutes=30), END + timedelta(minutes=30)),
        (START - timedelta(minutes=30), END + timedelta(minutes=30)),
    ):
        with pytest.raises(IntegrityError) as caught, transaction.atomic():
            Booking.objects.create(space=room, user=owner, start_at=start, end_at=end)
        assert caught.value.__cause__.diag.constraint_name == (
            "bookings_active_no_overlap"
        )
    adjacent = create_booking(
        space=room, user=owner, start_at=END, end_at=END + timedelta(hours=1)
    )
    other_space = create_booking(space=lab, user=owner, start_at=START, end_at=END)
    assert adjacent.pk != first.pk
    assert other_space.pk != first.pk
    assert Booking.objects.count() == 3


def test_raw_sql_cannot_insert_overlapping_active_booking(domain):
    room, _, owner, _, _ = domain
    create_booking(space=room, user=owner, start_at=START, end_at=END)
    with (
        pytest.raises(IntegrityError) as caught,
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """INSERT INTO bookings_booking
               (space_id, user_id, start_at, end_at, status, created_at)
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
            [room.pk, owner.pk, START, END, Booking.Status.ACTIVE],
        )
    assert caught.value.__cause__.diag.constraint_name == "bookings_active_no_overlap"
    assert Booking.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_database_checks_status_interval_cancellation_and_foreign_keys(domain):
    room, _, owner, _, _ = domain
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(space=room, user=owner, start_at=END, end_at=START)
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(space=room, user=owner, start_at=START, end_at=START)
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(
            space=room, user=owner, start_at=START, end_at=END, status="other"
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(
            space=room,
            user=owner,
            start_at=START,
            end_at=END,
            status=Booking.Status.CANCELLED,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(space_id=999999, user=owner, start_at=START, end_at=END)
    booking = create_booking(space=room, user=owner, start_at=START, end_at=END)
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.filter(pk=booking.pk).update(cancelled_at=timezone.now())
    with pytest.raises(ProtectedError):
        room.delete()
    with pytest.raises(ProtectedError):
        owner.delete()


def test_http_create_read_availability_agenda_cancel_and_rebook(domain):
    room, _, _, _, staff = domain
    client = client_for(staff)
    availability = window_url("booking-availability", room)
    agenda = window_url("booking-agenda", room)
    assert client.get(availability).json()["available"] is True
    assert client.get(agenda).json()["occupied"] == []

    before = timezone.now()
    created = post_json(client, reverse("bookings-list"), payload(room))
    after = timezone.now()
    assert created.status_code == 201
    data = created.json()
    assert set(data) == {
        "id",
        "space_id",
        "start_at",
        "end_at",
        "status",
        "created_at",
        "cancelled_at",
    }
    assert (data["space_id"], data["status"], data["cancelled_at"]) == (
        room.pk,
        "active",
        None,
    )
    assert before <= datetime.fromisoformat(data["created_at"]) <= after
    booking = Booking.objects.get(pk=data["id"])
    assert booking.user_id == staff.pk
    assert client.get(availability).json()["available"] is False
    assert client.get(agenda).json()["occupied"] == [
        {"start_at": data["start_at"], "end_at": data["end_at"]}
    ]
    assert client.get(reverse("bookings-list")).json() == [data]
    assert client.get(reverse("bookings-detail", args=[booking.pk])).json() == data

    conflict = post_json(client, reverse("bookings-list"), payload(room))
    assert conflict.status_code == 409
    assert conflict.json() == {
        "error": {
            "code": "BOOKING_CONFLICT",
            "message": "Horário indisponível para o espaço.",
            "details": {"space_id": room.pk},
        }
    }
    assert Booking.objects.count() == 1

    cancelled = post_json(client, reverse("bookings-cancel", args=[booking.pk]), {})
    assert cancelled.status_code == 200
    assert cancelled.json()["id"] == booking.pk
    assert cancelled.json()["status"] == "cancelled"
    cancelled_at = cancelled.json()["cancelled_at"]
    booking.refresh_from_db()
    assert booking.cancelled_at == datetime.fromisoformat(cancelled_at)
    assert client.get(availability).json()["available"] is True
    assert client.get(agenda).json()["occupied"] == []
    repeated = post_json(client, reverse("bookings-cancel", args=[booking.pk]), {})
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "BOOKING_ALREADY_CANCELLED"
    booking.refresh_from_db()
    assert booking.cancelled_at == datetime.fromisoformat(cancelled_at)

    replacement = post_json(client, reverse("bookings-list"), payload(room))
    assert replacement.status_code == 201
    assert replacement.json()["id"] != booking.pk
    assert Booking.objects.filter(status="cancelled").count() == 1
    assert Booking.objects.filter(status="active").count() == 1


@pytest.mark.parametrize(
    "bad_payload",
    [
        {},
        {"space_id": 1, "start_at": START.isoformat()},
        {"space_id": "1", "start_at": START.isoformat(), "end_at": END.isoformat()},
        {"space_id": True, "start_at": START.isoformat(), "end_at": END.isoformat()},
        {"space_id": 1, "start_at": "2026-11-20T10:00:00", "end_at": END.isoformat()},
        {"space_id": 1, "start_at": START.isoformat(), "end_at": "2026-11-20T11:00:00"},
        {"space_id": 1, "start_at": END.isoformat(), "end_at": START.isoformat()},
        {"space_id": 1, "start_at": START.isoformat(), "end_at": START.isoformat()},
        {
            "space_id": 1,
            "start_at": START.isoformat(),
            "end_at": END.isoformat(),
            "user_id": 99,
        },
        [],
    ],
)
def test_invalid_create_payload_returns_400_without_writes(domain, bad_payload):
    _, _, _, _, staff = domain
    client = client_for(staff)
    response = post_json(client, reverse("bookings-list"), bad_payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert not Booking.objects.exists()


def test_missing_space_and_invalid_windows(domain):
    room, _, _, _, staff = domain
    client = client_for(staff)
    missing = post_json(
        client,
        reverse("bookings-list"),
        {
            "space_id": room.pk + 9999,
            "start_at": START.isoformat(),
            "end_at": END.isoformat(),
        },
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    for name in ("booking-availability", "booking-agenda"):
        assert client.get(reverse(name, args=[room.pk + 9999])).status_code == 404
        for query in (
            "",
            "?start_at=2026-11-20T10:00:00&end_at=2026-11-20T11:00:00",
            "?start_at=bad&end_at=bad",
        ):
            response = client.get(reverse(name, args=[room.pk]) + query)
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert not Booking.objects.exists()


def test_authentication_csrf_and_method_limits(domain):
    room, _, owner, _, staff = domain
    anonymous = Client(enforce_csrf_checks=True)
    assert anonymous.get(reverse("bookings-list")).status_code == 403
    assert anonymous.get(window_url("booking-availability", room)).status_code == 403
    assert anonymous.get(window_url("booking-agenda", room)).status_code == 403
    client = client_for(staff)
    assert (
        post_json(
            client, reverse("bookings-list"), payload(room), csrf=False
        ).status_code
        == 403
    )
    booking = create_booking(space=room, user=owner, start_at=START, end_at=END)
    cancel_url = reverse("bookings-cancel", args=[booking.pk])
    assert post_json(client, cancel_url, {}, csrf=False).status_code == 403
    assert client.get(cancel_url).status_code == 405
    assert (
        post_json(client, reverse("bookings-detail", args=[booking.pk]), {}).status_code
        == 405
    )
    booking.refresh_from_db()
    assert booking.status == "active"
    assert Booking.objects.count() == 1


def test_student_cannot_access_booking_records_but_can_read_occupancy(domain):
    room, lab, owner, other, staff = domain
    mine = create_booking(space=room, user=owner, start_at=START, end_at=END)
    theirs = create_booking(space=lab, user=other, start_at=START, end_at=END)
    owner_client = client_for(owner)
    staff_client = client_for(staff)
    for response in (
        owner_client.get(reverse("bookings-list")),
        owner_client.get(reverse("bookings-list") + "?scope=all"),
        owner_client.get(reverse("bookings-detail", args=[mine.pk])),
        owner_client.get(reverse("bookings-detail", args=[theirs.pk])),
        owner_client.get(reverse("bookings-detail", args=[theirs.pk + 999])),
        post_json(owner_client, reverse("bookings-list"), payload(room)),
        post_json(owner_client, reverse("bookings-cancel", args=[mine.pk]), {}),
        post_json(owner_client, reverse("bookings-cancel", args=[theirs.pk]), {}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    assert Booking.objects.filter(pk=mine.pk, status="active").exists()
    assert Booking.objects.filter(pk=theirs.pk, status="active").exists()
    assert staff_client.get(reverse("bookings-list")).json() == []
    all_rows = staff_client.get(reverse("bookings-list") + "?scope=all").json()
    assert {row["id"] for row in all_rows} == {mine.pk, theirs.pk}
    assert (
        staff_client.get(reverse("bookings-detail", args=[theirs.pk])).status_code
        == 200
    )
    filtered = staff_client.get(
        reverse("bookings-list") + f"?scope=all&space_id={lab.pk}&status=active"
    ).json()
    assert [row["id"] for row in filtered] == [theirs.pk]
    assert all("user" not in row and "username" not in row for row in all_rows)
    assert all(
        set(row)
        == {
            "id",
            "space_id",
            "start_at",
            "end_at",
            "status",
            "created_at",
            "cancelled_at",
        }
        for row in all_rows
    )
    assert owner_client.get(window_url("booking-agenda", lab)).json()["occupied"] == [
        {"start_at": all_rows[0]["start_at"], "end_at": all_rows[0]["end_at"]}
    ]
    assert all(
        "user" not in row
        for row in owner_client.get(window_url("booking-agenda", lab)).json()[
            "occupied"
        ]
    )
    cancelled = post_json(staff_client, reverse("bookings-cancel", args=[mine.pk]), {})
    assert cancelled.status_code == 200
    assert mine.user_id == owner.pk
    assert Booking.objects.filter(pk=mine.pk, status="cancelled").exists()


def test_filters_and_cancellation_body_validation(domain):
    room, _, owner, _, staff = domain
    client = client_for(staff)
    booking = create_booking(space=room, user=owner, start_at=START, end_at=END)
    for query in (
        "?space_id=bad",
        "?status=other",
        "?scope=bad",
        "?scope=all&scope=mine",
        "?extra=1",
    ):
        response = client.get(reverse("bookings-list") + query)
        assert response.status_code == 400
    cancel_url = reverse("bookings-cancel", args=[booking.pk])
    for bad_body in ({"cancelled_at": START.isoformat()}, [], {"user_id": owner.pk}):
        assert post_json(client, cancel_url, bad_body).status_code == 400
    assert (
        post_json(
            client, reverse("bookings-cancel", args=[booking.pk + 999]), {}
        ).status_code
        == 404
    )
    booking.refresh_from_db()
    assert booking.status == "active"
    assert booking.cancelled_at is None


def test_adjacent_windows_and_other_spaces_are_available(domain):
    room, lab, owner, _, staff = domain
    create_booking(space=room, user=owner, start_at=START, end_at=END)
    client = client_for(staff)
    adjacent = window_url(
        "booking-availability", room, start=END, end=END + timedelta(hours=1)
    )
    assert client.get(adjacent).json()["available"] is True
    assert (
        client.get(window_url("booking-availability", lab)).json()["available"] is True
    )
    assert (
        post_json(
            client,
            reverse("bookings-list"),
            payload(room, start=END, end=END + timedelta(hours=1)),
        ).status_code
        == 201
    )
    assert post_json(client, reverse("bookings-list"), payload(lab)).status_code == 201


def test_query_limits_and_agenda_order(domain, monkeypatch):
    room, _, owner, _, staff = domain
    client = client_for(staff)
    for hours in (2, 0, 1):
        create_booking(
            space=room,
            user=owner,
            start_at=START + timedelta(hours=hours),
            end_at=END + timedelta(hours=hours),
        )
    agenda_url = window_url("booking-agenda", room, end=END + timedelta(hours=2))
    occupied = client.get(agenda_url).json()["occupied"]
    assert [datetime.fromisoformat(row["start_at"]) for row in occupied] == [
        START + timedelta(hours=hours) for hours in range(3)
    ]
    bookings_url = reverse("bookings-list")
    page = client.get(bookings_url + "?scope=all&limit=1&offset=1").json()
    assert len(page) == 1
    assert page[0]["start_at"] == occupied[1]["start_at"]
    for query in ("?limit=101", "?limit=0", "?offset=-1"):
        assert client.get(bookings_url + query).status_code == 400

    too_long = window_url("booking-availability", room, end=START + timedelta(days=32))
    assert client.get(too_long).status_code == 400
    too_long = window_url("booking-agenda", room, end=START + timedelta(days=32))
    assert client.get(too_long).status_code == 400

    monkeypatch.setattr("apps.bookings.api.MAX_AGENDA_EVENTS", 2)
    response = client.get(agenda_url)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.django_db(transaction=True)
def test_concurrent_http_bookings_one_wins(domain):
    room, _, owner, other, _ = domain
    get_user_model().objects.filter(pk__in=[owner.pk, other.pk]).update(is_staff=True)
    clients = [client_for(owner), client_for(other)]
    gate = Barrier(2, timeout=10)
    url = reverse("bookings-list")

    def attempt(client):
        try:
            gate.wait()
            response = post_json(client, url, payload(room))
            return response.status_code, response.json()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, clients))
    assert sorted(code for code, _ in results) == [201, 409]
    assert (
        next(body for code, body in results if code == 409)["error"]["code"]
        == "BOOKING_CONFLICT"
    )
    assert Booking.objects.filter(space=room, status="active").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_http_bookings_in_different_spaces_both_succeed(domain):
    room, lab, owner, other, _ = domain
    get_user_model().objects.filter(pk__in=[owner.pk, other.pk]).update(is_staff=True)
    gate = Barrier(2, timeout=10)
    url = reverse("bookings-list")

    def attempt(user, space):
        client = client_for(user)
        try:
            gate.wait()
            return post_json(client, url, payload(space)).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda pair: attempt(*pair), [(owner, room), (other, lab)])
        )

    assert results == [201, 201]
    assert Booking.objects.filter(status=Booking.Status.ACTIVE).count() == 2
    assert Booking.objects.filter(space=room).count() == 1
    assert Booking.objects.filter(space=lab).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_cancellations_preserve_one_cancellation(domain):
    room, _, owner, _, staff = domain
    get_user_model().objects.filter(pk=owner.pk).update(is_staff=True)
    booking = create_booking(space=room, user=owner, start_at=START, end_at=END)
    clients = [client_for(owner), client_for(staff)]
    gate = Barrier(2, timeout=10)
    url = reverse("bookings-cancel", args=[booking.pk])

    def attempt(client):
        try:
            gate.wait()
            response = post_json(client, url, {})
            return response.status_code, response.json()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, clients))
    assert sorted(code for code, _ in results) == [200, 409]
    assert (
        next(body for code, body in results if code == 409)["error"]["code"]
        == "BOOKING_ALREADY_CANCELLED"
    )
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert booking.cancelled_at is not None
    assert Booking.objects.count() == 1


@pytest.mark.parametrize("error_type", [IntegrityError, OperationalError])
def test_unexpected_database_error_is_not_conflict(domain, monkeypatch, error_type):
    room, _, _, _, staff = domain
    client = client_for(staff, raise_request_exception=False)

    def fail(*args, **kwargs):
        raise error_type("falha inesperada")

    monkeypatch.setattr(Booking.objects, "create", fail)
    response = post_json(client, reverse("bookings-list"), payload(room))
    assert response.status_code == 500
    assert not Booking.objects.exists()


def test_cancel_rolls_back_after_save_failure(domain, monkeypatch):
    room, _, owner, _, staff = domain
    booking = create_booking(space=room, user=owner, start_at=START, end_at=END)
    client = client_for(staff, raise_request_exception=False)
    original_save = Booking.save

    def fail_after_save(self, *args, **kwargs):
        original_save(self, *args, **kwargs)
        raise IntegrityError("falha após gravar")

    monkeypatch.setattr(Booking, "save", fail_after_save)
    response = post_json(client, reverse("bookings-cancel", args=[booking.pk]), {})
    assert response.status_code == 500
    booking.refresh_from_db()
    assert booking.status == "active"
    assert booking.cancelled_at is None
    assert Booking.objects.count() == 1
