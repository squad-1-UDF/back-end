"""Carrega a base de demonstração (dados do squad de dados + logins de teste).

Só roda em banco vazio: se já existir algum espaço cadastrado, não faz nada.
A senha dos logins vem de LABTECH_SENHA_DEMO; sem ela, uma senha aleatória é
gerada e mostrada uma única vez no log.
"""

import os
import secrets
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.keys.models import Key
from apps.spaces.models import Space

SQL = Path(__file__).resolve().parents[2] / "demo" / "dados-demo.sql"

LOGINS = [
    ("ana.costa", "Ana", "Costa", "ana.costa@udf.edu.br", "admin"),
    ("rafael.nunes", "Rafael", "Nunes", "rafael.nunes@udf.edu.br", "employee"),
    ("joao.silva", "João", "Silva", "joao.silva@udf.edu.br", "student"),
]

ESPACOS = {
    "LAB-01": ("Laboratório de Informática 1", 30, "Bloco A, 1º andar"),
    "LAB-02": ("Laboratório de Informática 2", 30, "Bloco A, 1º andar"),
    "LAB-03": ("Laboratório de Informática 3", 25, "Bloco A, 2º andar"),
    "LAB-REDES": ("Laboratório de Redes", 20, "Bloco B, térreo"),
    "SALA-101": ("Sala 101", 40, "Bloco C, 1º andar"),
}


class Command(BaseCommand):
    help = "Carrega dados de demonstração e logins de teste em banco vazio."

    def handle(self, *args, **options):
        if Space.objects.exists():
            self.stdout.write("carregar_demo: banco já tem dados, nada a fazer.")
            return

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(SQL.read_text(encoding="utf-8"))
            self._ajustar_espacos_e_chaves()
            senha = os.getenv("LABTECH_SENHA_DEMO") or secrets.token_urlsafe(9)
            self._criar_logins(senha)

        self.stdout.write(
            "carregar_demo: dados carregados. Logins: "
            + ", ".join(u for u, *_ in LOGINS)
        )
        if not os.getenv("LABTECH_SENHA_DEMO"):
            self.stdout.write(f"carregar_demo: senha gerada para os logins: {senha}")

    def _ajustar_espacos_e_chaves(self):
        for space in Space.objects.all():
            nome, capacidade, local = ESPACOS.get(
                space.code,
                (space.code.replace("-", " ").title(), 30, "Campus UDF"),
            )
            Space.objects.filter(pk=space.pk).update(
                name=nome, capacity=capacidade, location=local
            )
        for key in Key.objects.select_related("space").order_by("space_id", "id"):
            numero = Key.objects.filter(space_id=key.space_id, id__lte=key.id).count()
            Key.objects.filter(pk=key.pk).update(label=f"{key.space.code}-{numero}")

    def _criar_logins(self, senha):
        user_model = get_user_model()
        grupo_admin, _ = Group.objects.get_or_create(name="admin")
        for username, nome, sobrenome, email, papel in LOGINS:
            user, _ = user_model.objects.get_or_create(username=username)
            user.first_name, user.last_name, user.email = nome, sobrenome, email
            user.is_active = True
            user.is_staff = papel in ("admin", "employee")
            user.set_password(senha)
            user.save()
            if papel == "admin":
                user.groups.add(grupo_admin)
