"""Integridade proposta pelo squad de dados (P6 de docs/dados/sql).

Fecha a brecha B6: o cancelamento não pode ser anterior à criação da reserva.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012 - formato de migration do Django
        ("bookings", "0001_initial"),
    ]

    operations = [  # noqa: RUF012 - formato de migration do Django
        # P6: CHECK em SQL (e não no Meta do model) para manter P1-P7 como
        # RunSQL reversível, exatamente como nas propostas originais.
        migrations.RunSQL(
            sql="""
                ALTER TABLE bookings_booking
                    ADD CONSTRAINT bookings_cancelled_after_created
                    CHECK (cancelled_at IS NULL OR cancelled_at >= created_at);
            """,
            reverse_sql="""
                ALTER TABLE bookings_booking
                    DROP CONSTRAINT bookings_cancelled_after_created;
            """,
        ),
    ]
