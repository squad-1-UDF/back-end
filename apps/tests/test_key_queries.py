from datetime import UTC, datetime

import pytest

from apps.keys.rules import (
    KeyCheckout,
    KeyReturn,
    active_loan_ref_for_key,
    has_active_loan,
    movements_for_key,
)


def at(hour: int) -> datetime:
    return datetime(2026, 10, 30, hour, tzinfo=UTC)


def test_key_never_checked_out_and_empty_history():
    assert not has_active_loan((), "key-a")
    assert active_loan_ref_for_key((), "key-a") is None
    assert movements_for_key((), "key-a") == ()


def test_active_loan_reference_and_input_immutability():
    checkout = KeyCheckout("loan-a", "key-a", "person-1", at(10))
    history = [checkout]

    assert has_active_loan(history, "key-a")
    assert active_loan_ref_for_key(history, "key-a") == "loan-a"
    assert not has_active_loan(history, "key-b")
    assert movements_for_key(history, "key-a") == (checkout,)
    assert movements_for_key(history, "key-a")[0] is checkout
    assert history == [checkout]


def test_returned_key_has_no_active_loan_but_retains_history():
    checkout = KeyCheckout("loan-a", "key-a", "person-1", at(10))
    key_return = KeyReturn("loan-a", at(11))
    history = (checkout, key_return)

    assert not has_active_loan(history, "key-a")
    assert active_loan_ref_for_key(history, "key-a") is None
    assert movements_for_key(history, "key-a") == history


def test_successive_loans_and_interleaved_keys_preserve_event_order():
    first_checkout = KeyCheckout("loan-a1", "key-a", "person-1", at(10))
    other_checkout = KeyCheckout("loan-b1", "key-b", "person-2", at(11))
    first_return = KeyReturn("loan-a1", at(12))
    second_checkout = KeyCheckout("loan-a2", "key-a", "person-3", at(13))
    other_return = KeyReturn("loan-b1", at(14))
    history = (
        first_checkout,
        other_checkout,
        first_return,
        second_checkout,
        other_return,
    )

    assert active_loan_ref_for_key(history, "key-a") == "loan-a2"
    assert not has_active_loan(history, "key-b")
    assert movements_for_key(history, "key-a") == (
        first_checkout,
        first_return,
        second_checkout,
    )
    assert movements_for_key(history, "key-b") == (other_checkout, other_return)

    completed = (*history, KeyReturn("loan-a2", at(15)))
    assert not has_active_loan(completed, "key-a")
    assert movements_for_key(completed, "key-a")[-1] == completed[-1]


@pytest.mark.parametrize(
    "history",
    [
        (KeyReturn("missing-loan", at(10)),),
        (
            KeyCheckout("loan-a", "key-a", "person-1", at(10)),
            KeyCheckout("loan-a", "key-b", "person-2", at(11)),
        ),
        (
            KeyCheckout("loan-a", "key-a", "person-1", at(10)),
            KeyCheckout("loan-b", "key-a", "person-2", at(11)),
        ),
        (
            KeyCheckout("loan-a", "key-a", "person-1", at(11)),
            KeyReturn("loan-a", at(10)),
        ),
    ],
)
def test_queries_reject_inconsistent_history_even_for_another_key(history):
    for query in (has_active_loan, active_loan_ref_for_key, movements_for_key):
        with pytest.raises(ValueError):
            query(history, "key-other")


def test_queries_reject_invalid_key_reference():
    with pytest.raises(ValueError, match="Chave"):
        has_active_loan((), None)
    with pytest.raises(ValueError, match="Chave"):
        movements_for_key((), " ")
    with pytest.raises(TypeError, match="hashable"):
        active_loan_ref_for_key((), [])


def test_queries_reject_unknown_event_after_matching_checkout():
    checkout = KeyCheckout("loan-a", "key-a", "person-1", at(10))
    history = [checkout, object()]
    original = tuple(history)

    for query in (has_active_loan, active_loan_ref_for_key, movements_for_key):
        with pytest.raises(TypeError, match="histórico"):
            query(history, "key-a")
    assert tuple(history) == original
