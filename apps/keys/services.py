"""Operações transacionais de chaves, empréstimos e cadastro (UC004–UC008)."""

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.db.models.functions import Trim, Upper
from django.utils import timezone

from apps.keys.models import Key, KeyLoan, KeyMovement
from apps.keys.rules import KeyCheckout, KeyReturn, register_checkout, register_return


class KeyNotAvailable(ValueError):
    """Chave fora de uso administrativo (manutenção, perdida ou inativa)."""

    def __init__(self, status):
        super().__init__(f"Chave indisponível: situação {status}.")
        self.status = status


class KeySpaceLocked(ValueError):
    """Chave com histórico de empréstimo não pode trocar de espaço."""


class DuplicateKeyLabel(ValueError):
    """Já existe chave com o mesmo rótulo (sem diferenciar maiúsculas)."""


def normalize_label(label):
    return label.strip().upper()


def _label_taken(label, *, exclude_pk=None):
    keys = Key.objects.annotate(normalized=Upper(Trim("label"))).filter(
        normalized=normalize_label(label)
    )
    if exclude_pk is not None:
        keys = keys.exclude(pk=exclude_pk)
    return keys.exists()


def is_duplicate_label(exc):
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == "keys_key_label_unique_ci"


def is_space_locked(exc):
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == "keys_key_space_fixed_after_loan"


@transaction.atomic
def create_key(*, space, label, status=Key.Status.AVAILABLE):
    label = label.strip()
    if _label_taken(label):
        raise DuplicateKeyLabel(label)
    try:
        with transaction.atomic():
            return Key.objects.create(space=space, label=label, status=status)
    except IntegrityError as exc:
        # Corrida entre dois cadastros: o índice único decide.
        if is_duplicate_label(exc):
            raise DuplicateKeyLabel(label) from exc
        raise


@transaction.atomic
def update_key(*, key_id, changes):
    """Atualiza label, status e/ou espaço, bloqueando a linha da chave."""
    key = Key.objects.select_for_update().get(pk=key_id)
    if "label" in changes:
        changes = {**changes, "label": changes["label"].strip()}
        if _label_taken(changes["label"], exclude_pk=key.pk):
            raise DuplicateKeyLabel(changes["label"])
    if (
        "space" in changes
        and changes["space"].pk != key.space_id
        and KeyLoan.objects.filter(key_id=key.pk).exists()
    ):
        raise KeySpaceLocked("Chave com histórico não pode mudar de espaço.")
    if not changes:
        return key
    try:
        with transaction.atomic():
            # A linha já está bloqueada; o UPDATE direto evita repetir no save().
            Key.objects.filter(pk=key.pk).update(**changes)
    except IntegrityError as exc:
        if is_duplicate_label(exc):
            raise DuplicateKeyLabel(changes.get("label", "")) from exc
        if is_space_locked(exc):
            raise KeySpaceLocked(
                "Chave com histórico não pode mudar de espaço."
            ) from exc
        raise
    key.refresh_from_db()
    return key


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
    if key.status != Key.Status.AVAILABLE:
        raise KeyNotAvailable(key.status)
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


def keys_with_active_loan():
    """Chaves com espaço e empréstimo ativo (em `active_loans`) já carregados."""
    active = KeyLoan.objects.filter(returned_at__isnull=True).select_related(
        "responsible"
    )
    return (
        Key.objects.select_related("space")
        .prefetch_related(Prefetch("loans", queryset=active, to_attr="active_loans"))
        .annotate(
            is_loaned=Exists(
                KeyLoan.objects.filter(key=OuterRef("pk"), returned_at__isnull=True)
            )
        )
        .order_by("id")
    )


def loans_with_relations():
    return KeyLoan.objects.select_related("key__space", "responsible").order_by(
        "-checked_out_at", "-id"
    )
