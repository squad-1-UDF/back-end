"""Integridade proposta pelo squad de dados (P7 de docs/dados/sql).

Fecha as brechas B7 e B8: o código do espaço passa a ser único sem
diferenciar maiúsculas nem espaços nas pontas, também em gravações diretas.
Se já houver duplicados normalizados, a criação do índice falha e a migration
não é aplicada; antes, confira com:
SELECT upper(btrim(code)), count(*) FROM spaces_space GROUP BY 1 HAVING count(*) > 1;
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012 - formato de migration do Django
        ("spaces", "0001_initial"),
    ]

    operations = [  # noqa: RUF012 - formato de migration do Django
        # P7: código único normalizado (B7 maiúsculas, B8 espaços nas pontas).
        migrations.RunSQL(
            sql="""
                CREATE UNIQUE INDEX spaces_space_code_normalized_uniq
                ON spaces_space (upper(btrim(code)));
            """,
            reverse_sql="DROP INDEX spaces_space_code_normalized_uniq;",
        ),
    ]
