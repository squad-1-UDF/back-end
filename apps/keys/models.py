"""Persistência de chaves, empréstimos e movimentações."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q


class Key(models.Model):
    id = models.BigAutoField(primary_key=True)
    space = models.ForeignKey(
        "spaces.Space", on_delete=models.PROTECT, related_name="keys"
    )

    def save(self, *args, **kwargs):
        if self.pk:
            with transaction.atomic():
                previous = type(self).objects.select_for_update().get(pk=self.pk)
                if (
                    previous.space_id != self.space_id
                    and KeyLoan.objects.filter(key_id=self.pk).exists()
                ):
                    raise ValidationError(
                        "Chave com histórico não pode mudar de espaço."
                    )
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class KeyLoan(models.Model):
    id = models.BigAutoField(primary_key=True)
    key = models.ForeignKey(Key, on_delete=models.PROTECT, related_name="loans")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsible_key_loans",
    )
    checkout_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_key_checkouts",
    )
    checked_out_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    return_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registered_key_returns",
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=["key"],
                condition=Q(returned_at__isnull=True),
                name="keys_one_active_loan_per_key",
            ),
            models.CheckConstraint(
                condition=Q(returned_at__isnull=True)
                | Q(returned_at__gte=F("checked_out_at")),
                name="keys_return_not_before_checkout",
            ),
            models.CheckConstraint(
                condition=(
                    Q(returned_at__isnull=True) & Q(return_operator__isnull=True)
                )
                | (Q(returned_at__isnull=False) & Q(return_operator__isnull=False)),
                name="keys_return_time_operator_together",
            ),
        ]


class KeyMovement(models.Model):
    class Kind(models.TextChoices):
        CHECKOUT = "checkout", "Retirada"
        RETURN = "return", "Devolução"

    id = models.BigAutoField(primary_key=True)
    loan = models.ForeignKey(
        KeyLoan, on_delete=models.PROTECT, related_name="movements"
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    occurred_at = models.DateTimeField()
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="key_movements"
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=Q(kind__in=["checkout", "return"]),
                name="keys_movement_kind_valid",
            ),
            models.UniqueConstraint(
                fields=["loan", "kind"], name="keys_one_movement_per_loan_kind"
            ),
        ]
