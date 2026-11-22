"""Rótulo e situação administrativa das chaves (UC004)."""

import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012 - formato de migration do Django
        ("keys", "0002_integridade"),
    ]

    operations = [  # noqa: RUF012 - formato de migration do Django
        migrations.AddField(
            model_name="key",
            name="label",
            field=models.CharField(default="", max_length=40),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="key",
            name="status",
            field=models.CharField(
                choices=[
                    ("available", "Disponível"),
                    ("maintenance", "Em manutenção"),
                    ("lost", "Perdida"),
                    ("inactive", "Inativa"),
                ],
                db_default="available",
                default="available",
                max_length=12,
            ),
        ),
        # Chaves existentes recebem CHAVE-<id> antes da unicidade do rótulo.
        migrations.RunSQL(
            sql="UPDATE keys_key SET label = 'CHAVE-' || id WHERE btrim(label) = '';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddConstraint(
            model_name="key",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Upper(
                    django.db.models.functions.text.Trim("label")
                ),
                name="keys_key_label_unique_ci",
            ),
        ),
        migrations.AddConstraint(
            model_name="key",
            constraint=models.CheckConstraint(
                condition=models.Q(("label__regex", "[^[:space:]]")),
                name="keys_key_label_nonblank",
            ),
        ),
        migrations.AddConstraint(
            model_name="key",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status__in", ["available", "maintenance", "lost", "inactive"])
                ),
                name="keys_key_status_valid",
            ),
        ),
    ]
