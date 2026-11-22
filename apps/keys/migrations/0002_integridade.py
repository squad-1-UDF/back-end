"""Integridade proposta pelo squad de dados (P1-P5 de docs/dados/sql).

Brechas fechadas no banco (veja docs/dados/inconsistencias-e-sugestoes.md):
- P1 (B4, B5): os dados da retirada não mudam e a devolução não é desfeita;
- P2 (B1, B3): o movimento precisa bater com o empréstimo;
- P3 (B2): todo empréstimo tem movimento de retirada e, se devolvido, de
  devolução. É um constraint trigger DEFERRED: só confere no COMMIT, depois que
  ``checkout_key``/``return_key`` gravaram empréstimo e movimento;
- P4 (B10): a retirada não pode ser registrada no futuro (tolerância de 5 min);
- P5 (B9): o responsável precisa estar ativo no momento da retirada.

A ordem de gravação de apps/keys/services.py (empréstimo e depois movimento)
continua válida, sem mudança no Python.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [  # noqa: RUF012 - formato de migration do Django
        ("keys", "0001_initial"),
    ]

    operations = [  # noqa: RUF012 - formato de migration do Django
        # P1: congela os dados da retirada e a devolução já registrada.
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION keys_loan_guard_update() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.key_id IS DISTINCT FROM OLD.key_id
                       OR NEW.responsible_id IS DISTINCT FROM OLD.responsible_id
                       OR NEW.checkout_operator_id
                          IS DISTINCT FROM OLD.checkout_operator_id
                       OR NEW.checked_out_at IS DISTINCT FROM OLD.checked_out_at THEN
                        RAISE EXCEPTION 'Checkout data of a key loan cannot be changed'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_loan_checkout_immutable';
                    END IF;
                    IF OLD.returned_at IS NOT NULL
                       AND (NEW.returned_at IS DISTINCT FROM OLD.returned_at
                            OR NEW.return_operator_id
                               IS DISTINCT FROM OLD.return_operator_id) THEN
                        RAISE EXCEPTION 'A registered return cannot be changed or undone'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_loan_return_immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER keys_loan_guard_update
                BEFORE UPDATE ON keys_keyloan
                FOR EACH ROW EXECUTE FUNCTION keys_loan_guard_update();
            """,
            reverse_sql="""
                DROP TRIGGER keys_loan_guard_update ON keys_keyloan;
                DROP FUNCTION keys_loan_guard_update();
            """,
        ),
        # P2: movimento confere com o empréstimo (horário, operador, devolução).
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION keys_movement_matches_loan() RETURNS trigger
                LANGUAGE plpgsql AS $$
                DECLARE l keys_keyloan%ROWTYPE;
                BEGIN
                    SELECT * INTO l FROM keys_keyloan WHERE id = NEW.loan_id;
                    IF NOT FOUND THEN
                        RETURN NEW;  -- a FK (adiada) recusa no fim da transação
                    END IF;
                    IF NEW.kind = 'checkout'
                       AND (NEW.occurred_at <> l.checked_out_at
                            OR NEW.operator_id <> l.checkout_operator_id) THEN
                        RAISE EXCEPTION 'Checkout movement must match the loan checkout'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_movement_matches_loan';
                    END IF;
                    IF NEW.kind = 'return'
                       AND (l.returned_at IS NULL
                            OR NEW.occurred_at <> l.returned_at
                            OR NEW.operator_id <> l.return_operator_id) THEN
                        RAISE EXCEPTION
                            'Return movement must match a registered return of the loan'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_movement_matches_loan';
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER keys_movement_matches_loan
                BEFORE INSERT ON keys_keymovement
                FOR EACH ROW EXECUTE FUNCTION keys_movement_matches_loan();
            """,
            reverse_sql="""
                DROP TRIGGER keys_movement_matches_loan ON keys_keymovement;
                DROP FUNCTION keys_movement_matches_loan();
            """,
        ),
        # P3: empréstimo exige movimentos; conferido no COMMIT (DEFERRED).
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION keys_loan_has_movements() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM keys_keymovement
                        WHERE loan_id = NEW.id AND kind = 'checkout'
                    ) THEN
                        RAISE EXCEPTION 'Key loan % has no checkout movement', NEW.id
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_loan_requires_movements';
                    END IF;
                    IF NEW.returned_at IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM keys_keymovement
                        WHERE loan_id = NEW.id AND kind = 'return'
                    ) THEN
                        RAISE EXCEPTION
                            'Returned key loan % has no return movement', NEW.id
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_loan_requires_movements';
                    END IF;
                    RETURN NULL;
                END;
                $$;
                CREATE CONSTRAINT TRIGGER keys_loan_requires_movements
                AFTER INSERT OR UPDATE ON keys_keyloan
                DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION keys_loan_has_movements();
            """,
            reverse_sql="""
                DROP TRIGGER keys_loan_requires_movements ON keys_keyloan;
                DROP FUNCTION keys_loan_has_movements();
            """,
        ),
        # P4: retirada não pode estar no futuro (5 min de tolerância de relógio).
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION keys_loan_not_in_future() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.checked_out_at > now() + interval '5 minutes' THEN
                        RAISE EXCEPTION 'Key checkout cannot be in the future'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_loan_not_in_future';
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER keys_loan_not_in_future
                BEFORE INSERT ON keys_keyloan
                FOR EACH ROW EXECUTE FUNCTION keys_loan_not_in_future();
            """,
            reverse_sql="""
                DROP TRIGGER keys_loan_not_in_future ON keys_keyloan;
                DROP FUNCTION keys_loan_not_in_future();
            """,
        ),
        # P5: responsável ativo na retirada. "Operador precisa ser staff" (B11)
        # continua só na API (IsAdminUser), como na proposta original.
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION keys_loan_responsible_active() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NOT (
                        SELECT is_active FROM auth_user WHERE id = NEW.responsible_id
                    ) THEN
                        RAISE EXCEPTION
                            'Inactive user cannot be responsible for a key loan'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'keys_loan_responsible_active';
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER keys_loan_responsible_active
                BEFORE INSERT ON keys_keyloan
                FOR EACH ROW EXECUTE FUNCTION keys_loan_responsible_active();
            """,
            reverse_sql="""
                DROP TRIGGER keys_loan_responsible_active ON keys_keyloan;
                DROP FUNCTION keys_loan_responsible_active();
            """,
        ),
    ]
