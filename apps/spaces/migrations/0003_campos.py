"""Campos descritivos e desativação de espaços (UC003)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012 - formato de migration do Django
        ("spaces", "0002_integridade"),
    ]

    operations = [  # noqa: RUF012 - formato de migration do Django
        migrations.AddField(
            model_name="space",
            name="name",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=120
            ),
        ),
        migrations.AddField(
            model_name="space",
            name="capacity",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="space",
            name="location",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=120
            ),
        ),
        migrations.AddField(
            model_name="space",
            name="is_active",
            field=models.BooleanField(db_default=True, default=True),
        ),
        migrations.AddConstraint(
            model_name="space",
            constraint=models.CheckConstraint(
                condition=models.Q(("capacity__isnull", True))
                | models.Q(("capacity__gt", 0)),
                name="spaces_space_capacity_positive",
            ),
        ),
    ]
