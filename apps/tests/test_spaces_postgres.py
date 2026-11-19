"""UC003: validações Django e integridade real no PostgreSQL de teste."""

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, connection, transaction

from apps.spaces.models import Space

database = settings.DATABASES["default"]
if database["ENGINE"] == "django.db.backends.postgresql":
    allowed_targets = {
        ("labtech_local", "127.0.0.1", "55432"),
        ("labtech_local", "127.0.0.1", "56432"),
        ("labtech_ci", "127.0.0.1", "5432"),
    }
    target = (database["NAME"], database["HOST"], str(database["PORT"]))
    if target not in allowed_targets or database["TEST"]["NAME"] != (
        f"test_{database['NAME']}"
    ):
        raise RuntimeError("UC003 integrada exige o PostgreSQL local ou efêmero da CI.")

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        database["ENGINE"] != "django.db.backends.postgresql",
        reason="UC003 integrada exige PostgreSQL local ou da CI",
    ),
]


def insert_direct(*, code, kind):
    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO "spaces_space" ("code", "kind") VALUES (%s, %s)',
            [code, kind],
        )


@pytest.mark.parametrize(
    ("code", "kind"),
    [("SALA-01", Space.Kind.ROOM), ("LAB-01", Space.Kind.LABORATORY)],
)
def test_space_creation_and_retrieval(code, kind):
    space = Space.objects.create(code=code, kind=kind)

    assert isinstance(space.pk, int)
    recovered = Space.objects.get(pk=space.pk)
    assert recovered.code == code
    assert recovered.kind == kind


def test_code_is_unique_through_orm_and_direct_sql():
    Space.objects.create(code="SALA-01", kind=Space.Kind.ROOM)

    with pytest.raises(IntegrityError), transaction.atomic():
        Space.objects.create(code="SALA-01", kind=Space.Kind.LABORATORY)
    with pytest.raises(IntegrityError), transaction.atomic():
        insert_direct(code="SALA-01", kind="room")

    assert Space.objects.filter(code="SALA-01").count() == 1


@pytest.mark.parametrize(
    ("code", "kind"),
    [("", "room"), ("   ", "room"), ("LAB-01", "other")],
)
def test_django_full_clean_rejects_invalid_values(code, kind):
    with pytest.raises(ValidationError):
        Space(code=code, kind=kind).full_clean()


@pytest.mark.parametrize(
    ("code", "kind", "constraint"),
    [
        ("", "room", "spaces_space_code_nonblank"),
        (" \t\n", "room", "spaces_space_code_nonblank"),
        ("LAB-01", "other", "spaces_space_kind_valid"),
    ],
)
def test_postgresql_constraints_reject_direct_sql(code, kind, constraint):
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        insert_direct(code=code, kind=kind)

    assert error.value.__cause__.diag.constraint_name == constraint


def test_code_length_is_validated_by_django_and_postgresql():
    code = "X" * 51
    with pytest.raises(ValidationError):
        Space(code=code, kind="room").full_clean()
    with pytest.raises(DataError), transaction.atomic():
        insert_direct(code=code, kind="room")


@pytest.mark.parametrize(("code", "kind"), [(None, "room"), ("SALA-01", None)])
def test_required_columns_reject_null_in_postgresql(code, kind):
    with pytest.raises(IntegrityError), transaction.atomic():
        insert_direct(code=code, kind=kind)
