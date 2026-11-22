-- =============================================================================
-- LabTech: PROPOSTAS de regras de integridade (NÃO aplicadas no back-end)
-- Fecham as brechas encontradas por validacao-integridade.sql.
-- São sugestões para o back-end avaliar e, se aprovadas, levar para uma migration
-- (RunSQL com reverse_sql). Testadas só num PostgreSQL local descartável:
--   psql -d <banco_local> -f sql/schema-labtech.sql
--   psql -d <banco_local> -f sql/propostas-integridade.sql
--   psql -d <banco_local> -f sql/dados-demo.sql
--   psql -d <banco_local> -f sql/validacao-integridade.sql
-- Compatível com a ordem de gravação atual de apps/keys/services.py
-- (cria o empréstimo e depois o movimento; na devolução, atualiza o empréstimo e depois grava o movimento).
-- =============================================================================

-- P1. Empréstimo: dados da retirada não mudam e devolução não é desfeita -------
CREATE FUNCTION keys_loan_guard_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.key_id IS DISTINCT FROM OLD.key_id
       OR NEW.responsible_id IS DISTINCT FROM OLD.responsible_id
       OR NEW.checkout_operator_id IS DISTINCT FROM OLD.checkout_operator_id
       OR NEW.checked_out_at IS DISTINCT FROM OLD.checked_out_at THEN
        RAISE EXCEPTION 'Checkout data of a key loan cannot be changed'
            USING ERRCODE = '23514', CONSTRAINT = 'keys_loan_checkout_immutable';
    END IF;
    IF OLD.returned_at IS NOT NULL
       AND (NEW.returned_at IS DISTINCT FROM OLD.returned_at
            OR NEW.return_operator_id IS DISTINCT FROM OLD.return_operator_id) THEN
        RAISE EXCEPTION 'A registered return cannot be changed or undone'
            USING ERRCODE = '23514', CONSTRAINT = 'keys_loan_return_immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER keys_loan_guard_update
BEFORE UPDATE ON keys_keyloan
FOR EACH ROW EXECUTE FUNCTION keys_loan_guard_update();

-- P2. Movimento confere com o empréstimo (horário, operador e devolução real) --
CREATE FUNCTION keys_movement_matches_loan() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE l keys_keyloan%ROWTYPE;
BEGIN
    SELECT * INTO l FROM keys_keyloan WHERE id = NEW.loan_id;
    IF NOT FOUND THEN
        RETURN NEW;  -- a FK (adiada) recusa no fim da transação
    END IF;
    IF NEW.kind = 'checkout'
       AND (NEW.occurred_at <> l.checked_out_at OR NEW.operator_id <> l.checkout_operator_id) THEN
        RAISE EXCEPTION 'Checkout movement must match the loan checkout'
            USING ERRCODE = '23514', CONSTRAINT = 'keys_movement_matches_loan';
    END IF;
    IF NEW.kind = 'return'
       AND (l.returned_at IS NULL OR NEW.occurred_at <> l.returned_at
            OR NEW.operator_id <> l.return_operator_id) THEN
        RAISE EXCEPTION 'Return movement must match a registered return of the loan'
            USING ERRCODE = '23514', CONSTRAINT = 'keys_movement_matches_loan';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER keys_movement_matches_loan
BEFORE INSERT ON keys_keymovement
FOR EACH ROW EXECUTE FUNCTION keys_movement_matches_loan();

-- P3. Todo empréstimo tem retirada registrada; todo devolvido tem devolução ----
-- (constraint trigger ADIADA: confere no COMMIT, depois que o serviço gravou os dois)
CREATE FUNCTION keys_loan_has_movements() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM keys_keymovement WHERE loan_id = NEW.id AND kind = 'checkout') THEN
        RAISE EXCEPTION 'Key loan % has no checkout movement', NEW.id
            USING ERRCODE = '23514', CONSTRAINT = 'keys_loan_requires_movements';
    END IF;
    IF NEW.returned_at IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM keys_keymovement WHERE loan_id = NEW.id AND kind = 'return') THEN
        RAISE EXCEPTION 'Returned key loan % has no return movement', NEW.id
            USING ERRCODE = '23514', CONSTRAINT = 'keys_loan_requires_movements';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER keys_loan_requires_movements
AFTER INSERT OR UPDATE ON keys_keyloan
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION keys_loan_has_movements();

-- P4. Retirada não pode ser registrada no futuro (tolerância de 5 min de relógio)
CREATE FUNCTION keys_loan_not_in_future() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.checked_out_at > now() + interval '5 minutes' THEN
        RAISE EXCEPTION 'Key checkout cannot be in the future'
            USING ERRCODE = '23514', CONSTRAINT = 'keys_loan_not_in_future';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER keys_loan_not_in_future
BEFORE INSERT ON keys_keyloan
FOR EACH ROW EXECUTE FUNCTION keys_loan_not_in_future();

-- P5. Responsável precisa estar ativo no momento da retirada --------------------
-- (o "operador precisa ser staff" já é exigido pela API via IsAdminUser; deixar no banco é opcional)
CREATE FUNCTION keys_loan_responsible_active() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT (SELECT is_active FROM auth_user WHERE id = NEW.responsible_id) THEN
        RAISE EXCEPTION 'Inactive user cannot be responsible for a key loan'
            USING ERRCODE = '23514', CONSTRAINT = 'keys_loan_responsible_active';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER keys_loan_responsible_active
BEFORE INSERT ON keys_keyloan
FOR EACH ROW EXECUTE FUNCTION keys_loan_responsible_active();

-- P6. Reserva: cancelamento não pode ser anterior à criação ---------------------
ALTER TABLE bookings_booking
    ADD CONSTRAINT bookings_cancelled_after_created
    CHECK (cancelled_at IS NULL OR cancelled_at >= created_at);

-- P7. Código do espaço único sem diferenciar maiúsculas nem espaços nas pontas --
-- (antes de aplicar, conferir se já há duplicados: SELECT upper(btrim(code)), count(*) FROM spaces_space GROUP BY 1 HAVING count(*) > 1)
CREATE UNIQUE INDEX spaces_space_code_normalized_uniq ON spaces_space (upper(btrim(code)));
