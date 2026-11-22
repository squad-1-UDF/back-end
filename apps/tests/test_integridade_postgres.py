"""Brechas B1-B10 do squad de dados fechadas pelas migrations 0002_integridade.

Os testes usam ``transaction=True``: cada ``transaction.atomic()`` externo faz
COMMIT de verdade, e só assim o constraint trigger adiado (P3) dispara como em
produção. Em testes comuns (``TestCase``), nada é comitado.
"""

import json
from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import cancel_booking, create_booking
from apps.keys.models import Key, KeyLoan, KeyMovement
from apps.keys.services import checkout_key, return_key
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
        raise RuntimeError("Integridade exige PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="Integridade exige PostgreSQL local ou da CI",
    ),
]


def violated(error_info):
    """Nome da constraint (ou trigger) que o PostgreSQL apontou no erro."""
    return error_info.value.__cause__.diag.constraint_name


@pytest.fixture
def domain():
    room = Space.objects.create(code="LAB-01", kind="laboratory")
    key = Key.objects.create(space=room)
    users = get_user_model().objects
    responsible = users.create_user(username="responsavel", password="segura-123")
    operator = users.create_user(username="operador", password="segura-456")
    return key, responsible, operator


@pytest.fixture
def past():
    return timezone.now() - timedelta(days=1)


@pytest.fixture
def returned_loan(domain, past):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=past
    )
    return return_key(
        loan_id=loan.pk, operator=operator, occurred_at=past + timedelta(hours=1)
    )


# --- Fluxo normal continua passando -------------------------------------------


def test_normal_key_flow_commits(domain):
    key, responsible, operator = domain
    for _ in range(2):
        loan = checkout_key(key_id=key.pk, responsible=responsible, operator=operator)
        loan = return_key(loan_id=loan.pk, operator=operator)
    assert KeyLoan.objects.filter(key=key, returned_at__isnull=False).count() == 2
    assert KeyMovement.objects.filter(loan__key=key).count() == 4
    active = checkout_key(key_id=key.pk, responsible=responsible, operator=operator)
    assert KeyLoan.objects.get(pk=active.pk).returned_at is None


def test_normal_flow_via_http(domain):
    key, responsible, _ = domain
    staff = get_user_model().objects.create_user(
        username="balcao", password="segura-789", is_staff=True
    )
    client = Client()
    client.force_login(staff)
    checkout = client.post(
        reverse("key-loans-checkout"),
        data=json.dumps({"key_id": key.pk, "responsible_user_id": responsible.pk}),
        content_type="application/json",
    )
    assert checkout.status_code == 201
    returned = client.post(
        reverse("key-loans-return", args=[checkout.json()["id"]]),
        data="{}",
        content_type="application/json",
    )
    assert returned.status_code == 200
    created = client.post(
        reverse("spaces-list"),
        data=json.dumps({"code": "lab-01", "kind": "room"}),
        content_type="application/json",
    )
    # B7 pela API: o índice normalizado vira 409, não 500.
    assert created.status_code == 409
    assert created.json()["error"]["code"] == "DUPLICATE_CODE"


def test_normal_booking_cancel_commits(domain):
    key, responsible, _ = domain
    start = timezone.now() + timedelta(days=1)
    booking = create_booking(
        space=key.space, user=responsible, start_at=start, end_at=start + timedelta(1)
    )
    cancel_booking(booking_id=booking.pk, actor=responsible)
    booking.refresh_from_db()
    assert booking.cancelled_at >= booking.created_at


# --- B1/B3 (P2): movimento precisa bater com o empréstimo ----------------------


def test_b1_return_movement_on_active_loan_is_rejected(domain, past):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=past
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        KeyMovement.objects.create(
            loan=loan, kind="return", occurred_at=timezone.now(), operator=operator
        )
    assert violated(error) == "keys_movement_matches_loan"
    assert list(loan.movements.values_list("kind", flat=True)) == ["checkout"]


@pytest.mark.parametrize("mismatch", ["time", "operator"])
def test_b3_checkout_movement_must_match_loan(domain, past, mismatch):
    key, responsible, operator = domain
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        loan = KeyLoan.objects.create(
            key=key,
            responsible=responsible,
            checkout_operator=operator,
            checked_out_at=past,
        )
        KeyMovement.objects.create(
            loan=loan,
            kind="checkout",
            occurred_at=past + timedelta(minutes=1) if mismatch == "time" else past,
            operator=responsible if mismatch == "operator" else operator,
        )
    assert violated(error) == "keys_movement_matches_loan"
    assert not KeyLoan.objects.exists()


# --- B2 (P3, adiado): empréstimo sem movimentos é recusado no COMMIT -----------


def test_b2_loan_without_checkout_movement_fails_on_commit(domain, past):
    key, responsible, operator = domain
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        KeyLoan.objects.create(
            key=key,
            responsible=responsible,
            checkout_operator=operator,
            checked_out_at=past,
        )
        # Dentro da transação o INSERT passa: a conferência é só no COMMIT.
        assert KeyLoan.objects.count() == 1
    assert violated(error) == "keys_loan_requires_movements"
    assert not KeyLoan.objects.exists()


def test_b2_returned_loan_without_return_movement_fails_on_commit(domain, past):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=past
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        KeyLoan.objects.filter(pk=loan.pk).update(
            returned_at=past + timedelta(hours=1), return_operator=operator
        )
    assert violated(error) == "keys_loan_requires_movements"
    assert KeyLoan.objects.get(pk=loan.pk).returned_at is None


# --- B4/B5 (P1): retirada congelada e devolução não é desfeita -----------------


@pytest.mark.parametrize("field", ["responsible", "checked_out_at", "operator"])
def test_b4_checkout_data_cannot_be_rewritten(domain, returned_loan, field):
    _, responsible, operator = domain
    changes = {
        "responsible": {"responsible": operator},
        "checked_out_at": {"checked_out_at": returned_loan.checked_out_at},
        "operator": {"checkout_operator": responsible},
    }[field]
    if field == "checked_out_at":
        changes["checked_out_at"] -= timedelta(minutes=5)
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        KeyLoan.objects.filter(pk=returned_loan.pk).update(**changes)
    assert violated(error) == "keys_loan_checkout_immutable"


def test_b4_active_loan_responsible_cannot_change(domain, past):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=past
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        KeyLoan.objects.filter(pk=loan.pk).update(responsible=operator)
    assert violated(error) == "keys_loan_checkout_immutable"


def test_b5_return_cannot_be_undone_or_changed(domain, returned_loan):
    _, responsible, _ = domain
    for changes in (
        {"returned_at": None, "return_operator": None},
        {"returned_at": returned_loan.returned_at + timedelta(minutes=1)},
        {"return_operator": responsible},
    ):
        with pytest.raises(IntegrityError) as error, transaction.atomic():
            KeyLoan.objects.filter(pk=returned_loan.pk).update(**changes)
        assert violated(error) == "keys_loan_return_immutable"
    assert KeyLoan.objects.get(pk=returned_loan.pk).returned_at is not None


# --- B6 (P6): cancelamento não antecede a criação ------------------------------


def test_b6_cancel_before_creation_is_rejected(domain):
    key, responsible, _ = domain
    start = timezone.now() + timedelta(days=1)
    booking = create_booking(
        space=key.space, user=responsible, start_at=start, end_at=start + timedelta(1)
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Booking.objects.filter(pk=booking.pk).update(
            status="cancelled", cancelled_at=booking.created_at - timedelta(hours=1)
        )
    assert violated(error) == "bookings_cancelled_after_created"


# --- B7/B8 (P7): código do espaço normalizado ----------------------------------


@pytest.mark.parametrize("code", ["lab-01", " LAB-01 ", "Lab-01  "])
def test_b7_b8_space_code_normalized_unique(domain, code):
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Space.objects.create(code=code, kind="room")
    assert violated(error) == "spaces_space_code_normalized_uniq"
    assert Space.objects.count() == 1


# --- B9 (P5): responsável ativo ------------------------------------------------


def test_b9_inactive_responsible_is_rejected(domain, past):
    key, responsible, operator = domain
    responsible.is_active = False
    responsible.save(update_fields=["is_active"])
    with pytest.raises(IntegrityError) as error:
        checkout_key(
            key_id=key.pk, responsible=responsible, operator=operator, occurred_at=past
        )
    assert violated(error) == "keys_loan_responsible_active"
    assert not KeyLoan.objects.exists()


# --- B10 (P4): retirada no futuro ----------------------------------------------


def test_b10_future_checkout_is_rejected_with_tolerance(domain):
    key, responsible, operator = domain
    with pytest.raises(IntegrityError) as error:
        checkout_key(
            key_id=key.pk,
            responsible=responsible,
            operator=operator,
            occurred_at=timezone.now() + timedelta(hours=1),
        )
    assert violated(error) == "keys_loan_not_in_future"
    # Diferença pequena de relógio (até 5 min) continua aceita.
    loan = checkout_key(
        key_id=key.pk,
        responsible=responsible,
        operator=operator,
        occurred_at=timezone.now() + timedelta(minutes=2),
    )
    assert KeyLoan.objects.filter(pk=loan.pk).exists()


# --- Migrations reversíveis ----------------------------------------------------


def db_objects():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tgname FROM pg_trigger
            WHERE tgname LIKE 'keys\\_%%' AND NOT tgisinternal
            UNION ALL
            SELECT indexname FROM pg_indexes
            WHERE indexname = 'spaces_space_code_normalized_uniq'
            UNION ALL
            SELECT conname FROM pg_constraint
            WHERE conname = 'bookings_cancelled_after_created'
            """
        )
        return {row[0] for row in cursor.fetchall()}


NEW_OBJECTS = {
    "keys_loan_guard_update",
    "keys_movement_matches_loan",
    "keys_loan_requires_movements",
    "keys_loan_not_in_future",
    "keys_loan_responsible_active",
    "spaces_space_code_normalized_uniq",
    "bookings_cancelled_after_created",
}


def test_integrity_migrations_are_reversible():
    operations = [
        (app, operation)
        for app in ("spaces", "keys", "bookings")
        for operation in import_module(
            f"apps.{app}.migrations.0002_integridade"
        ).Migration.operations
    ]
    assert all(operation.reversible for _, operation in operations)
    assert NEW_OBJECTS <= db_objects()
    with connection.schema_editor() as editor:
        for app, operation in reversed(operations):
            operation.database_backwards(app, editor, None, None)
    try:
        assert not (NEW_OBJECTS & db_objects())
    finally:
        with connection.schema_editor() as editor:
            for app, operation in operations:
                operation.database_forwards(app, editor, None, None)
    assert NEW_OBJECTS <= db_objects()
