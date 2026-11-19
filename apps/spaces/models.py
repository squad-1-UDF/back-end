"""Persistência mínima de salas e laboratórios (UC003)."""

from django.db import models
from django.db.models import Q


class Space(models.Model):
    class Kind(models.TextChoices):
        ROOM = "room", "Sala"
        LABORATORY = "laboratory", "Laboratório"

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=50, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)

    class Meta:
        constraints = [  # noqa: RUF012 - configuração declarativa do Django
            models.CheckConstraint(
                condition=Q(code__regex=r"[^[:space:]]"),
                name="spaces_space_code_nonblank",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["room", "laboratory"]),
                name="spaces_space_kind_valid",
            ),
        ]
