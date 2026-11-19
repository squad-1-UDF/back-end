"""UC004–UC008 com usuários reais e PostgreSQL de teste isolado."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from importlib import import_module
from threading import Barrier

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from apps.keys.models import Key, KeyLoan, KeyMovement
from apps.keys.services import (
    _rule_history,
    checkout_key,
    has_active_loan,
    movements_for_key,
    return_key,
)
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
        raise RuntimeError("UC004–UC008 exigem PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC004–UC008 exigem PostgreSQL local ou da CI",
    ),
]

AT = datetime(2026, 10, 30, 10, tzinfo=UTC)


@pytest.fixture
def domain():
    room = Space.objects.create(code="SALA-01", kind="room")
    key = Key.objects.create(space=room)
    user_model = get_user_model()
    responsible = user_model.objects.create_user(
        username="responsavel", password="segura-123"
    )
    operator = user_model.objects.create_user(
        username="operador", password="segura-456"
    )
    return key, responsible, operator


def test_create_checkout_return_history_and_availability(domain):
    key, responsible, operator = domain
    assert isinstance(key.pk, int)
    assert key.space_id == Space.objects.get(code="SALA-01").pk
    assert not has_active_loan(key)
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )
    assert loan.responsible_id != loan.checkout_operator_id
    assert has_active_loan(key)
    assert KeyLoan.objects.get(pk=loan.pk).checked_out_at == AT
    checkout = movements_for_key(key).get()
    assert (checkout.loan_id, checkout.kind, checkout.operator_id) == (
        loan.pk,
        "checkout",
        operator.pk,
    )

    returned = return_key(
        loan_id=loan.pk, operator=operator, occurred_at=AT + timedelta(hours=1)
    )
    assert returned.return_operator_id == operator.pk
    assert returned.returned_at == AT + timedelta(hours=1)
    assert not has_active_loan(key)
    assert list(movements_for_key(key).values_list("kind", flat=True)) == [
        "checkout",
        "return",
    ]
    with pytest.raises(ValueError, match="encerrado"):
        return_key(
            loan_id=loan.pk, operator=operator, occurred_at=AT + timedelta(hours=2)
        )
    assert KeyMovement.objects.count() == 2
    second = checkout_key(
        key_id=key.pk,
        responsible=responsible,
        operator=operator,
        occurred_at=AT + timedelta(hours=2),
    )
    assert second.pk != loan.pk
    assert has_active_loan(key)


def test_constraints_and_protected_relations(domain):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyLoan.objects.create(
            key=key,
            responsible=responsible,
            checkout_operator=operator,
            checked_out_at=AT,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyMovement.objects.create(
            loan=loan, kind="checkout", occurred_at=AT, operator=operator
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyMovement.objects.create(
            loan=loan, kind="other", occurred_at=AT, operator=operator
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        loan.returned_at = AT - timedelta(seconds=1)
        loan.save(update_fields=["returned_at"])
    loan.refresh_from_db()
    assert loan.returned_at is None
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyLoan.objects.filter(pk=loan.pk).update(returned_at=AT)
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyLoan.objects.filter(pk=loan.pk).update(return_operator=operator)
    with pytest.raises(ProtectedError):
        key.space.delete()
    with pytest.raises(ProtectedError):
        key.delete()
    with pytest.raises(ProtectedError):
        responsible.delete()


@pytest.mark.django_db(transaction=True)
def test_postgresql_rejects_orphan_foreign_keys(domain):
    key, responsible, operator = domain
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyLoan.objects.create(
            key_id=999999,
            responsible=responsible,
            checkout_operator=operator,
            checked_out_at=AT,
        )
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        KeyMovement.objects.create(
            loan_id=loan.pk + 999999,
            kind="return",
            occurred_at=AT,
            operator=operator,
        )


def test_services_reject_inconsistent_existing_movements(domain):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )
    KeyLoan.objects.filter(pk=loan.pk).update(checkout_operator=responsible)
    with pytest.raises(ValueError, match="inconsistente"):
        return_key(
            loan_id=loan.pk, operator=operator, occurred_at=AT + timedelta(hours=1)
        )
    assert KeyLoan.objects.get(pk=loan.pk).returned_at is None
    KeyLoan.objects.filter(pk=loan.pk).update(checkout_operator=operator)
    return_key(loan_id=loan.pk, operator=operator, occurred_at=AT + timedelta(hours=1))
    KeyLoan.objects.filter(pk=loan.pk).update(returned_at=AT)
    with pytest.raises(ValueError, match="inconsistente"):
        checkout_key(
            key_id=key.pk,
            responsible=responsible,
            operator=operator,
            occurred_at=AT + timedelta(hours=2),
        )
    assert KeyLoan.objects.count() == 1


@pytest.mark.parametrize("kind", ["checkout", "return"])
@pytest.mark.parametrize("action", ["update", "delete"])
def test_postgresql_rejects_direct_movement_changes(domain, kind, action):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )
    return_key(loan_id=loan.pk, operator=operator, occurred_at=AT + timedelta(hours=1))
    movement = KeyMovement.objects.get(loan=loan, kind=kind)
    original = (movement.occurred_at, movement.operator_id)

    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        if action == "update":
            cursor.execute(
                "UPDATE keys_keymovement SET occurred_at = %s WHERE id = %s",
                [AT + timedelta(days=1), movement.pk],
            )
        else:
            cursor.execute("DELETE FROM keys_keymovement WHERE id = %s", [movement.pk])

    movement.refresh_from_db()
    assert (movement.occurred_at, movement.operator_id) == original
    assert list(movements_for_key(key).values_list("kind", flat=True)) == [
        "checkout",
        "return",
    ]


@pytest.mark.parametrize(
    ("returned", "movement_kinds"),
    [
        (False, ()),
        (True, ()),
        (True, ("checkout",)),
        (True, ("return",)),
    ],
)
def test_history_rejects_loans_without_expected_movements(
    domain, returned, movement_kinds
):
    key, responsible, operator = domain
    loan = KeyLoan.objects.create(
        key=key,
        responsible=responsible,
        checkout_operator=operator,
        checked_out_at=AT,
        returned_at=AT + timedelta(hours=1) if returned else None,
        return_operator=operator if returned else None,
    )
    for kind in movement_kinds:
        KeyMovement.objects.create(
            loan=loan,
            kind=kind,
            occurred_at=AT if kind == "checkout" else AT + timedelta(hours=1),
            operator=operator,
        )

    with pytest.raises(ValueError, match="sem movimentação esperada"):
        _rule_history(key)
    with pytest.raises(ValueError, match="sem movimentação esperada"):
        checkout_key(
            key_id=key.pk,
            responsible=responsible,
            operator=operator,
            occurred_at=AT + timedelta(hours=2),
        )
    assert KeyLoan.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_movement_trigger_has_reversible_sql():
    migration = import_module("apps.keys.migrations.0001_initial").Migration
    operation = migration.operations[-1]

    def trigger_exists():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = %s)",
                ["keys_movement_immutable"],
            )
            return cursor.fetchone()[0]

    assert trigger_exists()
    with connection.schema_editor() as editor:
        operation.database_backwards("keys", editor, None, None)
    try:
        assert not trigger_exists()
    finally:
        with connection.schema_editor() as editor:
            operation.database_forwards("keys", editor, None, None)
    assert trigger_exists()


def test_key_cannot_move_after_history(domain):
    key, responsible, operator = domain
    checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )
    other = Space.objects.create(code="LAB-02", kind="laboratory")
    key.space = other
    with pytest.raises(ValidationError, match="histórico"):
        key.save()
    with pytest.raises(IntegrityError), transaction.atomic():
        Key.objects.filter(pk=key.pk).update(space=other)
    key.refresh_from_db()
    assert key.space.code == "SALA-01"


def test_checkout_rolls_back_if_movement_insert_fails(domain, monkeypatch):
    key, responsible, operator = domain

    def fail(*args, **kwargs):
        raise IntegrityError("falha na movimentação")

    monkeypatch.setattr(KeyMovement.objects, "create", fail)
    with pytest.raises(IntegrityError):
        checkout_key(
            key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
        )
    assert not KeyLoan.objects.exists()
    assert not has_active_loan(key)


def test_return_rolls_back_if_movement_insert_fails(domain, monkeypatch):
    key, responsible, operator = domain
    loan = checkout_key(
        key_id=key.pk, responsible=responsible, operator=operator, occurred_at=AT
    )

    def fail(*args, **kwargs):
        raise IntegrityError("falha na movimentação")

    monkeypatch.setattr(KeyMovement.objects, "create", fail)
    with pytest.raises(IntegrityError):
        return_key(
            loan_id=loan.pk, operator=operator, occurred_at=AT + timedelta(hours=1)
        )
    loan.refresh_from_db()
    assert loan.returned_at is None
    assert has_active_loan(key)
    assert list(movements_for_key(key).values_list("kind", flat=True)) == ["checkout"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkouts_leave_one_active_loan(domain):
    key, responsible, operator = domain
    gate = Barrier(2, timeout=10)

    def attempt():
        try:
            gate.wait()
            checkout_key(
                key_id=key.pk,
                responsible=responsible,
                operator=operator,
                occurred_at=AT,
            )
            return "created"
        except (ValueError, IntegrityError):
            return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ["created", "rejected"]
    assert KeyLoan.objects.filter(key=key, returned_at__isnull=True).count() == 1
    assert KeyMovement.objects.filter(loan__key=key).count() == 1
