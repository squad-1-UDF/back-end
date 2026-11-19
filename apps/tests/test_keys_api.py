from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APIClient

from apps.keys.serializers import KeySerializer


def test_listar_chaves_sem_autenticacao():
    client = APIClient()

    response = client.get(reverse("keys-list"))

    assert response.status_code in (401, 403)


def test_consultar_chave_sem_autenticacao():
    client = APIClient()

    response = client.get(reverse("keys-detail", kwargs={"key_id": "1"}))

    assert response.status_code in (401, 403)


def test_cadastrar_chave_sem_autenticacao():
    client = APIClient()

    response = client.post(
        reverse("keys-list"),
        {"space_id": "s1"},
        format="json",
    )

    assert response.status_code in (401, 403)


def test_atualizar_chave_sem_autenticacao():
    client = APIClient()

    response = client.patch(
        reverse("keys-detail", kwargs={"key_id": "1"}),
        {"space_id": "s2"},
        format="json",
    )

    assert response.status_code in (401, 403)


def test_serializer_aceita_space_id_valido():
    serializer = KeySerializer(data={"space_id": "s1"})

    assert serializer.is_valid()
    assert serializer.validated_data["space_id"] == "s1"


def test_serializer_rejeita_space_id_ausente():
    serializer = KeySerializer(data={})

    assert not serializer.is_valid()
    assert "space_id" in serializer.errors


def test_serializer_rejeita_space_id_vazio():
    serializer = KeySerializer(data={"space_id": ""})

    assert not serializer.is_valid()
    assert "space_id" in serializer.errors


def test_serializer_remove_espacos_extras():
    serializer = KeySerializer(data={"space_id": "  s1  "})

    assert serializer.is_valid()
    assert serializer.validated_data["space_id"] == "s1"


def test_cadastrar_chave_com_dados_invalidos():
    client = APIClient()

    with patch(
        "apps.keys.api.KeyListCreateView.permission_classes",
        [],
    ):
        response = client.post(
            reverse("keys-list"),
            {"space_id": ""},
            format="json",
        )

    assert response.status_code == 400
    assert "space_id" in response.data


def test_cadastrar_chave_com_dados_validos():
    client = APIClient()

    with patch(
        "apps.keys.api.KeyListCreateView.permission_classes",
        [],
    ):
        response = client.post(
            reverse("keys-list"),
            {"space_id": "s1"},
            format="json",
        )

    assert response.status_code == 503


def test_atualizar_chave_com_dados_invalidos():
    client = APIClient()

    with patch(
        "apps.keys.api.KeyDetailView.permission_classes",
        [],
    ):
        response = client.patch(
            reverse("keys-detail", kwargs={"key_id": "1"}),
            {"space_id": ""},
            format="json",
        )

    assert response.status_code == 400
    assert "space_id" in response.data


def test_atualizar_chave_com_dados_validos():
    client = APIClient()

    with patch(
        "apps.keys.api.KeyDetailView.permission_classes",
        [],
    ):
        response = client.patch(
            reverse("keys-detail", kwargs={"key_id": "1"}),
            {"space_id": "s2"},
            format="json",
        )

    assert response.status_code == 503


def test_listar_chaves_retorna_503():
    client = APIClient()

    with patch(
        "apps.keys.api.KeyListCreateView.permission_classes",
        [],
    ):
        response = client.get(reverse("keys-list"))

    assert response.status_code == 503
    assert "detail" in response.data


def test_consultar_chave_retorna_503():
    client = APIClient()

    with patch(
        "apps.keys.api.KeyDetailView.permission_classes",
        [],
    ):
        response = client.get(reverse("keys-detail", kwargs={"key_id": "1"}))

    assert response.status_code == 503
    assert "detail" in response.data
