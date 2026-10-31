from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from apps.keys.rules import (
    KeyCheckout,
    KeyReturn,
    register_checkout,
    register_return,
)

CHECKOUT_AT = datetime(2026, 10, 30, 10, tzinfo=UTC)
RETURN_AT = datetime(2026, 10, 30, 11, tzinfo=UTC)


def checkout(history=(), **changes):
    values = {
        "loan_ref": "loan-1",
        "key_ref": "key-1",
        "responsible_ref": "person-1",
        "occurred_at": CHECKOUT_AT,
    }
    values.update(changes)
    return register_checkout(history, **values)


def test_valid_checkout_preserves_input_and_responsible_reference():
    original = []
    result = checkout(original, responsible_ref=42)

    assert original == []
    assert result == (KeyCheckout("loan-1", "key-1", 42, CHECKOUT_AT),)
    with pytest.raises(FrozenInstanceError):
        result[0].responsible_ref = "another-person"


def test_key_with_active_loan_is_unavailable():
    history = checkout()

    with pytest.raises(ValueError, match="indisponível"):
        checkout(history, loan_ref="loan-2")

    assert len(history) == 1
    assert len(checkout(history, loan_ref="loan-2", key_ref="key-2")) == 2


@pytest.mark.parametrize("responsible_ref", [None, "", "   "])
def test_checkout_requires_responsible(responsible_ref):
    with pytest.raises(ValueError, match="Responsável"):
        checkout(responsible_ref=responsible_ref)


def test_valid_return_appends_event_and_releases_key():
    history = checkout()
    returned = register_return(history, loan_ref="loan-1", occurred_at=RETURN_AT)

    assert history == (KeyCheckout("loan-1", "key-1", "person-1", CHECKOUT_AT),)
    assert returned == (*history, KeyReturn("loan-1", RETURN_AT))
    assert len(checkout(returned, loan_ref="loan-2", occurred_at=RETURN_AT)) == 3


def test_duplicate_return_is_rejected_without_altering_history():
    returned = register_return(checkout(), loan_ref="loan-1", occurred_at=RETURN_AT)

    with pytest.raises(ValueError, match="inexistente ou já encerrado"):
        register_return(returned, loan_ref="loan-1", occurred_at=RETURN_AT)

    assert len(returned) == 2


def test_nonexistent_loan_cannot_be_returned():
    with pytest.raises(ValueError, match="inexistente ou já encerrado"):
        register_return(checkout(), loan_ref="loan-other", occurred_at=RETURN_AT)


def test_closed_loan_reference_cannot_be_reused():
    returned = register_return(checkout(), loan_ref="loan-1", occurred_at=RETURN_AT)

    with pytest.raises(ValueError, match="já utilizada"):
        checkout(returned, key_ref="key-2", occurred_at=RETURN_AT)
    with pytest.raises(ValueError, match="já utilizada"):
        checkout(checkout(), key_ref="key-2")


def test_return_time_must_not_precede_checkout_even_in_another_timezone():
    plus_two = timezone(timedelta(hours=2))
    before = datetime(2026, 10, 30, 11, 30, tzinfo=plus_two)
    same_instant = datetime(2026, 10, 30, 12, tzinfo=plus_two)

    with pytest.raises(ValueError, match="anterior"):
        register_return(checkout(), loan_ref="loan-1", occurred_at=before)
    returned = register_return(checkout(), loan_ref="loan-1", occurred_at=same_instant)
    assert len(returned) == 2


def test_events_require_timezone_and_valid_references():
    with pytest.raises(ValueError, match="timezone"):
        checkout(occurred_at=datetime(2026, 10, 30, 10))
    with pytest.raises(ValueError, match="timezone"):
        register_return(
            checkout(), loan_ref="loan-1", occurred_at=datetime(2026, 10, 30, 11)
        )
    with pytest.raises(ValueError, match="Empréstimo"):
        checkout(loan_ref=None)
    with pytest.raises(TypeError, match="hashable"):
        checkout(key_ref=[])


def test_invalid_history_is_rejected():
    with pytest.raises(ValueError, match="sem empréstimo ativo"):
        checkout((KeyReturn("loan-1", RETURN_AT),), loan_ref="loan-2")
    with pytest.raises(TypeError, match="histórico"):
        checkout((object(),), loan_ref="loan-2")


def test_new_events_cannot_precede_latest_history_event_or_mutate_input():
    history = list(
        register_return(checkout(), loan_ref="loan-1", occurred_at=RETURN_AT)
    )
    original = tuple(history)

    with pytest.raises(ValueError, match="último registro"):
        checkout(history, loan_ref="loan-2", occurred_at=CHECKOUT_AT)
    assert tuple(history) == original

    active_history = list(
        checkout(checkout(), loan_ref="loan-2", key_ref="key-2", occurred_at=RETURN_AT)
    )
    active_original = tuple(active_history)
    with pytest.raises(ValueError, match="último registro"):
        register_return(
            active_history,
            loan_ref="loan-1",
            occurred_at=CHECKOUT_AT + timedelta(minutes=30),
        )
    assert tuple(active_history) == active_original


@pytest.mark.parametrize(
    ("history", "error"),
    [
        (
            (
                KeyCheckout("loan-1", "key-1", "person-1", CHECKOUT_AT),
                KeyCheckout("loan-1", "key-2", "person-2", RETURN_AT),
            ),
            "Empréstimo duplicado",
        ),
        (
            (
                KeyCheckout("loan-1", "key-1", "person-1", CHECKOUT_AT),
                KeyCheckout("loan-2", "key-1", "person-2", RETURN_AT),
            ),
            "mais de um empréstimo ativo",
        ),
        (
            (
                KeyCheckout("loan-1", "key-1", "person-1", CHECKOUT_AT),
                KeyReturn("loan-1", RETURN_AT),
                KeyReturn("loan-1", RETURN_AT),
            ),
            "sem empréstimo ativo",
        ),
        (
            (
                KeyCheckout("loan-1", "key-1", "person-1", CHECKOUT_AT),
                KeyReturn("loan-1", CHECKOUT_AT - timedelta(minutes=1)),
            ),
            "anterior ao último registro",
        ),
    ],
)
def test_inconsistent_history_is_rejected_without_mutation(history, error):
    original = tuple(history)
    with pytest.raises(ValueError, match=error):
        checkout(history, loan_ref="loan-3", key_ref="key-3", occurred_at=RETURN_AT)
    assert history == original
