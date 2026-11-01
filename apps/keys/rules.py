"""Regras puras de retirada e devolução de chaves."""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime


def _validate_ref(value: Hashable, name: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} é obrigatório.")
    try:
        hash(value)
    except TypeError as exc:
        raise TypeError(f"{name} deve ser uma referência hashable.") from exc


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("A data/hora deve ser datetime.")
    if value.utcoffset() is None:
        raise ValueError("A data/hora deve ter timezone.")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class KeyCheckout:
    """Registro imutável de uma retirada."""

    loan_ref: Hashable
    key_ref: Hashable
    responsible_ref: Hashable
    occurred_at: datetime

    def __post_init__(self) -> None:
        _validate_ref(self.loan_ref, "Empréstimo")
        _validate_ref(self.key_ref, "Chave")
        _validate_ref(self.responsible_ref, "Responsável")
        _as_utc(self.occurred_at)


@dataclass(frozen=True, slots=True)
class KeyReturn:
    """Registro imutável de uma devolução vinculada à retirada."""

    loan_ref: Hashable
    occurred_at: datetime

    def __post_init__(self) -> None:
        _validate_ref(self.loan_ref, "Empréstimo")
        _as_utc(self.occurred_at)


type KeyMovement = KeyCheckout | KeyReturn


def _replay_history(
    history: tuple[KeyMovement, ...],
) -> tuple[
    dict[Hashable, KeyCheckout],
    dict[Hashable, KeyCheckout],
    dict[Hashable, KeyCheckout],
    datetime | None,
]:
    checkouts_by_ref: dict[Hashable, KeyCheckout] = {}
    active_loans: dict[Hashable, KeyCheckout] = {}
    active_by_key: dict[Hashable, KeyCheckout] = {}
    latest_at: datetime | None = None

    for movement in history:
        if not isinstance(movement, (KeyCheckout, KeyReturn)):
            raise TypeError("O histórico deve conter apenas retiradas e devoluções.")
        occurred_at = _as_utc(movement.occurred_at)
        if latest_at is not None and occurred_at < latest_at:
            raise ValueError("Evento anterior ao último registro do histórico.")
        latest_at = occurred_at

        if isinstance(movement, KeyCheckout):
            if movement.loan_ref in checkouts_by_ref:
                raise ValueError("Empréstimo duplicado no histórico.")
            if movement.key_ref in active_by_key:
                raise ValueError("Chave com mais de um empréstimo ativo.")
            checkouts_by_ref[movement.loan_ref] = movement
            active_loans[movement.loan_ref] = movement
            active_by_key[movement.key_ref] = movement
        elif isinstance(movement, KeyReturn):
            checkout = active_loans.get(movement.loan_ref)
            if checkout is None:
                raise ValueError("Devolução sem empréstimo ativo no histórico.")
            del active_loans[movement.loan_ref]
            del active_by_key[checkout.key_ref]

    return checkouts_by_ref, active_loans, active_by_key, latest_at


def register_checkout(
    history: Iterable[KeyMovement],
    *,
    loan_ref: Hashable,
    key_ref: Hashable,
    responsible_ref: Hashable,
    occurred_at: datetime,
) -> tuple[KeyMovement, ...]:
    """Adiciona retirada se a chave não tem empréstimo ativo."""
    checkout = KeyCheckout(loan_ref, key_ref, responsible_ref, occurred_at)
    movements = tuple(history)
    checkouts_by_ref, _, active_by_key, latest_at = _replay_history(movements)
    if latest_at is not None and _as_utc(checkout.occurred_at) < latest_at:
        raise ValueError("Retirada anterior ao último registro do histórico.")
    if checkout.loan_ref in checkouts_by_ref:
        raise ValueError("Referência de empréstimo já utilizada.")
    if checkout.key_ref in active_by_key:
        raise ValueError("Chave indisponível: empréstimo ativo.")
    return (*movements, checkout)


def register_return(
    history: Iterable[KeyMovement],
    *,
    loan_ref: Hashable,
    occurred_at: datetime,
) -> tuple[KeyMovement, ...]:
    """Adiciona devolução somente para um empréstimo ativo."""
    key_return = KeyReturn(loan_ref, occurred_at)
    movements = tuple(history)
    _, active_loans, _, latest_at = _replay_history(movements)
    checkout = active_loans.get(key_return.loan_ref)
    if checkout is None:
        raise ValueError("Empréstimo inexistente ou já encerrado.")
    if _as_utc(key_return.occurred_at) < _as_utc(checkout.occurred_at):
        raise ValueError("Devolução anterior à retirada.")
    if latest_at is not None and _as_utc(key_return.occurred_at) < latest_at:
        raise ValueError("Devolução anterior ao último registro do histórico.")
    return (*movements, key_return)


def active_loan_ref_for_key(
    history: Iterable[KeyMovement], key_ref: Hashable
) -> Hashable | None:
    """Retorna a referência do empréstimo ativo da chave, se existir."""
    _validate_ref(key_ref, "Chave")
    _, _, active_by_key, _ = _replay_history(tuple(history))
    checkout = active_by_key.get(key_ref)
    return None if checkout is None else checkout.loan_ref


def has_active_loan(history: Iterable[KeyMovement], key_ref: Hashable) -> bool:
    """Indica apenas ausência ou presença de empréstimo ativo da chave."""
    return active_loan_ref_for_key(history, key_ref) is not None


def movements_for_key(
    history: Iterable[KeyMovement], key_ref: Hashable
) -> tuple[KeyMovement, ...]:
    """Filtra retiradas e respectivas devoluções, preservando a ordem."""
    _validate_ref(key_ref, "Chave")
    movements = tuple(history)
    checkouts_by_ref, _, _, _ = _replay_history(movements)
    selected: list[KeyMovement] = []
    for movement in movements:
        checkout = (
            movement
            if isinstance(movement, KeyCheckout)
            else checkouts_by_ref[movement.loan_ref]
        )
        if checkout.key_ref == key_ref:
            selected.append(movement)
    return tuple(selected)
