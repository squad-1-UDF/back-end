"""Operações transacionais de chaves; sem contrato HTTP nesta etapa."""

from django.db import transaction
from django.utils import timezone

from apps.keys.models import Key, KeyLoan, KeyMovement
from apps.keys.rules import KeyCheckout, KeyReturn, register_checkout, register_return


def movements_for_key(key):
    return KeyMovement.objects.filter(loan__key=key).order_by("occurred_at", "id")


def _rule_history(key):
    expected = {
        loan_id: {"checkout", "return"} if returned_at is not None else {"checkout"}
        for loan_id, returned_at in KeyLoan.objects.filter(key=key).values_list(
            "id", "returned_at"
        )
    }
    history = []
    for movement in movements_for_key(key).select_related("loan"):
        loan = movement.loan
        if movement.kind == KeyMovement.Kind.CHECKOUT:
            if (
                movement.occurred_at != loan.checked_out_at
                or movement.operator_id != loan.checkout_operator_id
            ):
                raise ValueError("Movimentação de retirada inconsistente.")
            history.append(
                KeyCheckout(loan.pk, key.pk, loan.responsible_id, movement.occurred_at)
            )
        else:
            if (
                movement.occurred_at != loan.returned_at
                or movement.operator_id != loan.return_operator_id
            ):
                raise ValueError("Movimentação de devolução inconsistente.")
            history.append(KeyReturn(loan.pk, movement.occurred_at))
        expected[loan.pk].discard(movement.kind)
    if any(missing for missing in expected.values()):
        raise ValueError("Empréstimo sem movimentação esperada no histórico.")
    return tuple(history)


def has_active_loan(key):
    """Disponibilidade lógica: ausência de empréstimo ativo."""
    return KeyLoan.objects.filter(key=key, returned_at__isnull=True).exists()


@transaction.atomic
def checkout_key(*, key_id, responsible, operator, occurred_at=None):
    key = Key.objects.select_for_update().get(pk=key_id)
    occurred_at = occurred_at or timezone.now()
    history = _rule_history(key)
    loan = KeyLoan.objects.create(
        key=key,
        responsible=responsible,
        checkout_operator=operator,
        checked_out_at=occurred_at,
    )
    register_checkout(
        history,
        loan_ref=loan.pk,
        key_ref=key.pk,
        responsible_ref=responsible.pk,
        occurred_at=occurred_at,
    )
    KeyMovement.objects.create(
        loan=loan,
        kind=KeyMovement.Kind.CHECKOUT,
        occurred_at=occurred_at,
        operator=operator,
    )
    return loan


@transaction.atomic
def return_key(*, loan_id, operator, occurred_at=None):
    loan = KeyLoan.objects.get(pk=loan_id)
    key = Key.objects.select_for_update().get(pk=loan.key_id)
    loan = KeyLoan.objects.select_for_update().get(pk=loan_id)
    occurred_at = occurred_at or timezone.now()
    register_return(_rule_history(key), loan_ref=loan.pk, occurred_at=occurred_at)
    loan.returned_at = occurred_at
    loan.return_operator = operator
    loan.save(update_fields=["returned_at", "return_operator"])
    KeyMovement.objects.create(
        loan=loan,
        kind=KeyMovement.Kind.RETURN,
        occurred_at=occurred_at,
        operator=operator,
    )
    return loan
