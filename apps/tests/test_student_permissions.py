"""Permissões do estudante nas rotas de reservas e chaves, sem banco."""

from types import SimpleNamespace

import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.parametrize(
    "method,name,args,payload",
    [
        ("get", "bookings-list", (), None),
        ("post", "bookings-list", (), {}),
        ("get", "bookings-detail", (1,), None),
        ("post", "bookings-cancel", (1,), {}),
        ("get", "keys-list", (), None),
        ("post", "keys-list", (), {}),
        ("get", "keys-detail", (1,), None),
        ("patch", "keys-detail", (1,), {}),
        ("get", "key-loans-checkout", (), None),
        ("post", "key-loans-checkout", (), {}),
        ("post", "key-loans-return", (1,), {}),
        ("get", "key-loan-availability", (1,), None),
        ("get", "key-movements", (1,), None),
    ],
)
def test_student_is_forbidden_before_domain_lookup(method, name, args, payload):
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True, is_staff=False))
    url = reverse(name, args=args)
    response = getattr(client, method)(url, payload, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
