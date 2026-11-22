"""Testes sem banco do cadastro de chaves.

Adaptados da estrutura inicial do PR feature/keys-api (rotas keys-list e
keys-detail e validação do KeySerializer), agora com space_id inteiro.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.keys.serializers import KeyFilters, KeySerializer


def test_listar_chaves_sem_autenticacao():
    response = APIClient().get(reverse("keys-list"))
    assert response.status_code in (401, 403)


def test_consultar_chave_sem_autenticacao():
    response = APIClient().get(reverse("keys-detail", kwargs={"key_id": 1}))
    assert response.status_code in (401, 403)


def test_cadastrar_chave_sem_autenticacao():
    response = APIClient().post(
        reverse("keys-list"), {"space_id": 1, "label": "LAB-01-A"}, format="json"
    )
    assert response.status_code in (401, 403)


def test_atualizar_chave_sem_autenticacao():
    response = APIClient().patch(
        reverse("keys-detail", kwargs={"key_id": 1}), {"space_id": 2}, format="json"
    )
    assert response.status_code in (401, 403)


def test_listar_emprestimos_sem_autenticacao():
    response = APIClient().get(reverse("key-loans-checkout"))
    assert response.status_code in (401, 403)


def test_serializer_aceita_dados_validos_e_remove_espacos():
    serializer = KeySerializer(data={"space_id": 1, "label": "  LAB-01-A  "})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"space_id": 1, "label": "LAB-01-A"}


@pytest.mark.parametrize(
    "data,field",
    [
        ({"label": "X"}, "space_id"),
        ({"space_id": "s1", "label": "X"}, "space_id"),
        ({"space_id": 1}, "label"),
        ({"space_id": 1, "label": ""}, "label"),
        ({"space_id": 1, "label": "A" * 41}, "label"),
        ({"space_id": 1, "label": "X", "status": "sumida"}, "status"),
    ],
)
def test_serializer_rejeita_dados_invalidos(data, field):
    serializer = KeySerializer(data=data)
    assert not serializer.is_valid()
    assert field in serializer.errors


def test_serializer_parcial_aceita_somente_status():
    serializer = KeySerializer(data={"status": "maintenance"}, partial=True)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"status": "maintenance"}


def test_filtro_converte_has_active_loan():
    from django.http import QueryDict

    filters = KeyFilters(data=QueryDict("has_active_loan=false&status=lost"))
    assert filters.is_valid(), filters.errors
    assert filters.validated_data == {"has_active_loan": False, "status": "lost"}
