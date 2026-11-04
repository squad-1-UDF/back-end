from types import SimpleNamespace

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.spaces.serializers import SpaceSerializer


def test_listar_espacos_sem_autenticacao():
    client = APIClient()
    response = client.get(reverse("spaces-list"))
    assert response.status_code in (401, 403)


def test_consultar_espaco_sem_autenticacao():
    client = APIClient()
    response = client.get(reverse("spaces-detail", kwargs={"space_id": "1"}))
    assert response.status_code in (401, 403)


def test_cadastrar_espaco_sem_autenticacao():
    client = APIClient()
    response = client.post(
        reverse("spaces-list"),
        {"code": "LAB01", "kind": "laboratory"},
        format="json",
    )
    assert response.status_code in (401, 403)


def test_atualizar_espaco_sem_autenticacao():
    client = APIClient()
    response = client.patch(
        reverse("spaces-detail", kwargs={"space_id": "1"}),
        {"code": "LAB02"},
        format="json",
    )
    assert response.status_code in (401, 403)


def test_espaco_com_codigo_vazio():
    serializer = SpaceSerializer(data={"code": "", "kind": "laboratory"})
    assert not serializer.is_valid()
    assert "code" in serializer.errors


def test_espaco_sem_identificacao():
    serializer = SpaceSerializer(data={"kind": "room"})
    assert not serializer.is_valid()
    assert "code" in serializer.errors


def test_espaco_com_tipo_invalido():
    serializer = SpaceSerializer(data={"code": "LAB01", "kind": "biblioteca"})
    assert not serializer.is_valid()
    assert "kind" in serializer.errors


def test_espaco_com_codigo_muito_longo():
    serializer = SpaceSerializer(data={"code": "A" * 51, "kind": "laboratory"})
    assert not serializer.is_valid()
    assert "code" in serializer.errors


def test_espaco_com_dados_validos():
    serializer = SpaceSerializer(data={"code": "LAB01", "kind": "laboratory"})
    assert serializer.is_valid()
    assert serializer.validated_data["code"] == "LAB01"
    assert serializer.validated_data["kind"] == "laboratory"


@pytest.mark.parametrize(
    "dados",
    [
        {"code": "", "kin": "laboratory"},
        {"kind": "room"},
        {"code": "LAB01", "kind": "biblioteca"},
        {"code": "A" * 51, "kind": "laboratory"},
    ],
)
def test_post_rejeita_dados_invalidos(dados):
    client = APIClient()
    usuario = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
    )
    client.force_authenticate(user=usuario)
    response = client.post(
        reverse("spaces-list"),
        dados,
        format="json",
    )
    assert response.status_code == 400


def test_post_com_dados_validos_sem_banco():
    client = APIClient()
    usuario = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
    )
    client.force_authenticate(user=usuario)
    response = client.post(
        reverse("spaces-list"),
        {
            "code": "LAB01",
            "kind": "laboratory",
        },
        format="json",
    )
    assert response.status_code == 503
    assert response.data["detail"] == "Cadastro ainda não disponível."
