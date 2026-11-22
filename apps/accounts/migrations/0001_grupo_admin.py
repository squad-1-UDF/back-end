"""Cria o grupo ``admin`` usado para derivar o papel de administrador (UC002)."""

from django.db import migrations


def criar_grupo_admin(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="admin")


def remover_grupo_admin(apps, schema_editor):
    # Só remove se ninguém estiver no grupo, para não perder papéis atribuídos.
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="admin", user__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012 - formato de migration do Django
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [  # noqa: RUF012 - formato de migration do Django
        migrations.RunPython(criar_grupo_admin, remover_grupo_admin),
    ]
