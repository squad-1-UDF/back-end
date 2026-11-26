"""UC004 (cadastro de chaves) e listagem de empréstimos com PostgreSQL isolado."""

from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from apps.keys.models import Key, KeyLoan
from apps.keys.services import checkout_key, return_key
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
        raise RuntimeError("UC004 exige PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC004 exige PostgreSQL local ou da CI",
    ),
]

PASSWORD = "senha-forte-123"
AT = datetime(2026, 10, 30, 10, tzinfo=UTC)
KEY_FIELDS = {
    "id",
    "space_id",
    "space_code",
    "label",
    "status",
    "has_active_loan",
    "active_loan",
}


@pytest.fixture
def people():
    user_model = get_user_model()
    staff = user_model.objects.create_user(
        username="operador", password=PASSWORD, is_staff=True
    )
    ordinary = user_model.objects.create_user(
        username="comum", password=PASSWORD, first_name="Ana", last_name="Costa"
    )
    return staff, ordinary


@pytest.fixture
def spaces():
    return (
        Space.objects.create(code="LAB-01", kind="laboratory"),
        Space.objects.create(code="SALA-02", kind="room"),
    )


def login_client(user):
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    response = client.post(
        reverse("auth-login"),
        {"identifier": user.username, "password": PASSWORD},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200
    return client


def write(client, method, url, payload, *, csrf=True):
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value} if csrf else {}
    return getattr(client, method)(
        url, payload, content_type="application/json", **headers
    )


def detail(key_id):
    return reverse("keys-detail", args=[key_id])


# Permissões


def test_anonymous_cannot_read_or_write_keys_or_loans(spaces):
    key = Key.objects.create(space=spaces[0], label="L1")
    client = Client(enforce_csrf_checks=True)
    assert client.get(reverse("auth-csrf")).status_code == 204
    responses = [
        client.get(reverse("keys-list")),
        client.get(detail(key.pk)),
        client.get(reverse("key-loans-checkout")),
        write(client, "post", reverse("keys-list"), {"space_id": 1, "label": "X"}),
        write(client, "patch", detail(key.pk), {"label": "X"}),
    ]
    for response in responses:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    assert Key.objects.get(pk=key.pk).label == "L1"


def test_regular_user_cannot_read_or_write_keys_or_loans(people, spaces):
    _, ordinary = people
    key = Key.objects.create(space=spaces[0], label="L1")
    client = login_client(ordinary)
    for response in (
        client.get(reverse("keys-list")),
        client.get(detail(key.pk)),
        client.get(detail(key.pk + 9999)),
        write(client, "post", reverse("keys-list"), {"space_id": 1, "label": "X"}),
        write(client, "patch", detail(key.pk), {"status": "lost"}),
        client.get(reverse("key-loans-checkout")),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    key.refresh_from_db()
    assert (key.label, key.status) == ("L1", "available")
    assert Key.objects.count() == 1


def test_staff_writes_require_csrf(people, spaces):
    staff, _ = people
    key = Key.objects.create(space=spaces[0], label="L1")
    client = login_client(staff)
    payload = {"space_id": spaces[0].pk, "label": "L2"}
    assert (
        write(client, "post", reverse("keys-list"), payload, csrf=False).status_code
        == 403
    )
    assert (
        write(client, "patch", detail(key.pk), {"label": "L3"}, csrf=False).status_code
        == 403
    )
    assert list(Key.objects.values_list("label", flat=True)) == ["L1"]


# Cadastro e edição


def test_staff_creates_reads_and_patches_key(people, spaces):
    staff, _ = people
    lab, room = spaces
    client = login_client(staff)
    created = write(
        client,
        "post",
        reverse("keys-list"),
        {"space_id": lab.pk, "label": " lab-01-a "},
    )
    assert created.status_code == 201
    data = created.json()
    assert data == {
        "id": data["id"],
        "space_id": lab.pk,
        "space_code": "LAB-01",
        "label": "lab-01-a",
        "status": "available",
        "has_active_loan": False,
        "active_loan": None,
    }
    assert client.get(detail(data["id"])).json() == data

    with_status = write(
        client,
        "post",
        reverse("keys-list"),
        {"space_id": room.pk, "label": "SALA-02-A", "status": "maintenance"},
    )
    assert with_status.status_code == 201
    assert with_status.json()["status"] == "maintenance"

    patched = write(
        client,
        "patch",
        detail(data["id"]),
        {"label": "LAB-01-B", "status": "lost", "space_id": room.pk},
    )
    assert patched.status_code == 200
    assert patched.json() == {
        **data,
        "label": "LAB-01-B",
        "status": "lost",
        "space_id": room.pk,
        "space_code": "SALA-02",
    }
    key = Key.objects.get(pk=data["id"])
    assert (key.label, key.status, key.space_id) == ("LAB-01-B", "lost", room.pk)

    # PATCH vazio não muda nada; reenviar o próprio rótulo não é duplicidade.
    assert write(client, "patch", detail(key.pk), {}).json() == patched.json()
    same = write(client, "patch", detail(key.pk), {"label": "lab-01-b"})
    assert same.status_code == 200
    assert same.json()["label"] == "lab-01-b"


@pytest.mark.parametrize("label", ["CHAVE-A", "chave-a", "  Chave-A  ", "\tCHAVE-a\n"])
def test_duplicate_label_ignoring_case_and_spaces_returns_400(people, spaces, label):
    staff, _ = people
    Key.objects.create(space=spaces[0], label="Chave-A")
    other = Key.objects.create(space=spaces[1], label="Chave-B")
    client = login_client(staff)

    created = write(
        client, "post", reverse("keys-list"), {"space_id": spaces[1].pk, "label": label}
    )
    assert created.status_code == 400
    error = created.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert error["details"] == {"label": ["Já existe uma chave com este rótulo."]}
    assert Key.objects.count() == 2

    patched = write(client, "patch", detail(other.pk), {"label": label})
    assert patched.status_code == 400
    assert patched.json()["error"]["details"]["label"]
    other.refresh_from_db()
    assert other.label == "Chave-B"


def test_database_unique_index_ignores_case_and_outer_spaces(spaces):
    Key.objects.create(space=spaces[0], label="ABC")
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Key.objects.create(space=spaces[1], label=" abc ")
    assert error.value.__cause__.diag.constraint_name == "keys_key_label_unique_ci"
    with (
        pytest.raises(IntegrityError) as error,
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO keys_key (space_id, label) VALUES (%s, '   ')",
            [spaces[0].pk],
        )
    assert error.value.__cause__.diag.constraint_name == "keys_key_label_nonblank"
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Key.objects.filter(label="ABC").update(status="sumida")
    assert error.value.__cause__.diag.constraint_name == "keys_key_status_valid"


def test_key_without_label_gets_default_pattern(spaces):
    key = Key.objects.create(space=spaces[0])
    assert key.label == f"CHAVE-{key.pk}"
    assert Key.objects.get(pk=key.pk).label == f"CHAVE-{key.pk}"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"label": "SEM-ESPACO"},
        {"space_id": 1},
        {"space_id": 1, "label": ""},
        {"space_id": 1, "label": "   "},
        {"space_id": 1, "label": "A" * 41},
        {"space_id": "1", "label": "X"},
        {"space_id": True, "label": "X"},
        {"space_id": 1, "label": "X", "status": "sumida"},
        {"space_id": 1, "label": "X", "id": 9},
        ["X"],
    ],
)
def test_invalid_create_returns_400_without_writes(people, spaces, payload):
    staff, _ = people
    if isinstance(payload, dict) and type(payload.get("space_id")) is int:
        payload = {**payload, "space_id": spaces[0].pk}
    response = write(login_client(staff), "post", reverse("keys-list"), payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "details" in response.json()["error"]
    assert not Key.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [{"label": ""}, {"label": "A" * 41}, {"status": "sumida"}, {"space_id": "2"}],
)
def test_invalid_patch_returns_400_without_writes(people, spaces, payload):
    staff, _ = people
    key = Key.objects.create(space=spaces[0], label="L1")
    response = write(login_client(staff), "patch", detail(key.pk), payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    key.refresh_from_db()
    assert (key.label, key.status, key.space_id) == ("L1", "available", spaces[0].pk)


def test_missing_key_or_space_returns_404(people, spaces):
    staff, _ = people
    key = Key.objects.create(space=spaces[0], label="L1")
    client = login_client(staff)
    missing_space = spaces[1].pk + 9999
    for response in (
        client.get(detail(key.pk + 9999)),
        client.get(detail(2**63)),
        write(client, "patch", detail(key.pk + 9999), {"label": "X"}),
        write(
            client,
            "post",
            reverse("keys-list"),
            {"space_id": missing_space, "label": "X"},
        ),
        write(client, "patch", detail(key.pk), {"space_id": missing_space}),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    assert Key.objects.get(pk=key.pk).space_id == spaces[0].pk


def test_space_change_with_loan_history_returns_409(people, spaces):
    staff, ordinary = people
    key = Key.objects.create(space=spaces[0], label="L1")
    loan = checkout_key(key_id=key.pk, responsible=ordinary, operator=staff)
    return_key(loan_id=loan.pk, operator=staff)
    client = login_client(staff)
    response = write(client, "patch", detail(key.pk), {"space_id": spaces[1].pk})
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "KEY_SPACE_LOCKED",
            "message": "Chave com histórico de empréstimo não pode mudar de espaço.",
            "details": {"key_id": key.pk},
        }
    }
    assert Key.objects.get(pk=key.pk).space_id == spaces[0].pk
    # Outros campos continuam editáveis, e o mesmo espaço não é troca.
    ok = write(
        client, "patch", detail(key.pk), {"space_id": spaces[0].pk, "status": "lost"}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "lost"


# Listagem e empréstimo ativo


def test_list_filters_and_active_loan(people, spaces):
    staff, ordinary = people
    lab, room = spaces
    k1 = Key.objects.create(space=lab, label="K1")
    k2 = Key.objects.create(space=lab, label="K2", status="maintenance")
    k3 = Key.objects.create(space=room, label="K3")
    loan = checkout_key(
        key_id=k3.pk, responsible=ordinary, operator=staff, occurred_at=AT
    )
    client = login_client(staff)
    url = reverse("keys-list")

    def ids(query=""):
        response = client.get(url + query)
        assert response.status_code == 200
        return [item["id"] for item in response.json()]

    assert ids() == [k1.pk, k2.pk, k3.pk]
    assert ids(f"?space_id={lab.pk}") == [k1.pk, k2.pk]
    assert ids("?status=maintenance") == [k2.pk]
    assert ids("?has_active_loan=true") == [k3.pk]
    assert ids("?has_active_loan=false") == [k1.pk, k2.pk]
    assert ids(f"?space_id={lab.pk}&status=available&has_active_loan=false") == [k1.pk]
    assert ids(f"?space_id={room.pk + 9999}") == []

    items = {item["id"]: item for item in client.get(url).json()}
    assert all(set(item) == KEY_FIELDS for item in items.values())
    assert items[k1.pk]["has_active_loan"] is False
    assert items[k1.pk]["active_loan"] is None
    assert items[k3.pk]["has_active_loan"] is True
    assert items[k3.pk]["active_loan"] == {
        "id": loan.pk,
        "responsible_user_id": ordinary.pk,
        "responsible_name": "Ana Costa",
        "checked_out_at": items[k3.pk]["active_loan"]["checked_out_at"],
    }
    assert datetime.fromisoformat(items[k3.pk]["active_loan"]["checked_out_at"]) == AT
    assert client.get(detail(k3.pk)).json() == items[k3.pk]

    return_key(loan_id=loan.pk, operator=staff)
    returned = client.get(detail(k3.pk)).json()
    assert (returned["has_active_loan"], returned["active_loan"]) == (False, None)
    assert ids("?has_active_loan=true") == []


@pytest.mark.parametrize(
    "query",
    [
        "?status=sumida",
        "?has_active_loan=1",
        "?space_id=abc",
        "?space_id=0",
        "?space_id=1&space_id=2",
        "?outro=1",
    ],
)
def test_invalid_key_filters_return_400(people, query):
    staff, _ = people
    response = login_client(staff).get(reverse("keys-list") + query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


# Retirada bloqueada por situação administrativa


@pytest.mark.parametrize("key_status", ["maintenance", "lost", "inactive"])
def test_checkout_of_unavailable_key_returns_409(people, spaces, key_status):
    staff, ordinary = people
    key = Key.objects.create(space=spaces[0], label="L1", status=key_status)
    client = login_client(staff)
    response = write(
        client,
        "post",
        reverse("key-loans-checkout"),
        {"key_id": key.pk, "responsible_user_id": ordinary.pk},
    )
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "KEY_UNAVAILABLE",
            "message": "Chave fora de uso para retirada.",
            "details": {"key_id": key.pk, "status": key_status},
        }
    }
    assert not KeyLoan.objects.exists()

    # Ao voltar a "available", a retirada é permitida.
    assert (
        write(client, "patch", detail(key.pk), {"status": "available"}).status_code
        == 200
    )
    allowed = write(
        client,
        "post",
        reverse("key-loans-checkout"),
        {"key_id": key.pk, "responsible_user_id": ordinary.pk},
    )
    assert allowed.status_code == 201


def test_return_is_allowed_even_if_key_left_available_status(people, spaces):
    staff, ordinary = people
    key = Key.objects.create(space=spaces[0], label="L1")
    loan = checkout_key(key_id=key.pk, responsible=ordinary, operator=staff)
    client = login_client(staff)
    assert (
        write(client, "patch", detail(key.pk), {"status": "maintenance"}).status_code
        == 200
    )
    response = write(client, "post", reverse("key-loans-return", args=[loan.pk]), {})
    assert response.status_code == 200
    assert response.json()["status"] == "returned"


# GET /key-loans/


def test_loan_list_filters_order_and_pagination(people, spaces):
    staff, ordinary = people
    lab, room = spaces
    k1 = Key.objects.create(space=lab, label="K1")
    k2 = Key.objects.create(space=room, label="K2")
    first = checkout_key(
        key_id=k1.pk, responsible=ordinary, operator=staff, occurred_at=AT
    )
    return_key(loan_id=first.pk, operator=staff, occurred_at=AT + timedelta(hours=1))
    second = checkout_key(
        key_id=k2.pk,
        responsible=staff,
        operator=staff,
        occurred_at=AT + timedelta(hours=2),
    )
    third = checkout_key(
        key_id=k1.pk,
        responsible=ordinary,
        operator=staff,
        occurred_at=AT + timedelta(hours=3),
    )
    client = login_client(staff)
    url = reverse("key-loans-checkout")

    def ids(query=""):
        response = client.get(url + query)
        assert response.status_code == 200
        return [item["id"] for item in response.json()]

    assert ids() == [third.pk, second.pk, first.pk]
    assert ids("?status=active") == [third.pk, second.pk]
    assert ids("?status=returned") == [first.pk]
    assert ids(f"?key_id={k1.pk}") == [third.pk, first.pk]
    assert ids(f"?space_id={room.pk}") == [second.pk]
    assert ids(f"?responsible_user_id={ordinary.pk}") == [third.pk, first.pk]
    assert ids(f"?responsible_user_id={ordinary.pk}&status=active") == [third.pk]
    assert ids("?limit=1") == [third.pk]
    assert ids("?limit=1&offset=1") == [second.pk]
    assert ids("?offset=5") == []

    returned = client.get(url + "?status=returned").json()[0]
    assert returned == {
        "id": first.pk,
        "key_id": k1.pk,
        "key_label": "K1",
        "space_id": lab.pk,
        "space_code": "LAB-01",
        "responsible_user_id": ordinary.pk,
        "responsible_name": "Ana Costa",
        "checkout_operator_id": staff.pk,
        "checked_out_at": returned["checked_out_at"],
        "returned_at": returned["returned_at"],
        "return_operator_id": staff.pk,
        "status": "returned",
    }
    assert datetime.fromisoformat(returned["returned_at"]) == AT + timedelta(hours=1)
    active = client.get(url + f"?space_id={room.pk}").json()[0]
    assert (active["status"], active["returned_at"], active["return_operator_id"]) == (
        "active",
        None,
        None,
    )
    assert active["responsible_name"] == "operador"


@pytest.mark.parametrize(
    "query",
    [
        "?status=cancelled",
        "?limit=0",
        "?limit=101",
        "?offset=-1",
        "?key_id=abc",
        "?status=active&status=returned",
        "?scope=all",
    ],
)
def test_invalid_loan_filters_return_400(people, query):
    staff, _ = people
    response = login_client(staff).get(reverse("key-loans-checkout") + query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


# Migration keys.0003_campos


@pytest.mark.django_db(transaction=True)
def test_migration_fills_existing_keys_with_default_label():
    executor = MigrationExecutor(connection)
    executor.migrate([("keys", "0001_initial")])
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO spaces_space (code, kind) VALUES ('MIG-01', 'room') "
                "RETURNING id"
            )
            space_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO keys_key (space_id) VALUES (%s), (%s) RETURNING id",
                [space_id, space_id],
            )
            key_ids = [row[0] for row in cursor.fetchall()]
        executor = MigrationExecutor(connection)
        executor.migrate([("keys", "0003_campos")])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, label, status FROM keys_key ORDER BY id",
            )
            rows = cursor.fetchall()
        assert rows == [(key_id, f"CHAVE-{key_id}", "available") for key_id in key_ids]
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
