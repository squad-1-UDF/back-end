-- =============================================================================
-- LabTech: validação da integridade da modelagem
-- Rodar num banco LOCAL descartável, depois de schema-labtech.sql e dados-demo.sql:
--   psql -d labtech_dados -f sql/validacao-integridade.sql
-- Cada teste roda dentro de um bloco que desfaz tudo no fim (o banco não muda).
--   [OK]     o banco se comportou como a regra exige
--   [BRECHA] o banco ACEITOU algo que a regra de negócio não permite (inconsistência)
--   [FALHA]  uma regra que deveria existir no banco não funcionou
-- =============================================================================
\set ON_ERROR_STOP on
SET client_min_messages = notice;

CREATE OR REPLACE FUNCTION pg_temp.deve_falhar(rotulo text, comando text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE comando;
        RAISE NOTICE '[FALHA]  %  -> deveria ser recusado e o banco ACEITOU', rotulo;
        RAISE EXCEPTION 'desfazer';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'desfazer' THEN
            RAISE NOTICE '[OK]     %  -> recusado: %', rotulo, SQLERRM;
        END IF;
    END;
END;
$$;

CREATE OR REPLACE FUNCTION pg_temp.deve_passar(rotulo text, comando text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE comando;
        RAISE NOTICE '[OK]     %  -> aceito', rotulo;
        RAISE EXCEPTION 'desfazer';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'desfazer' THEN
            RAISE NOTICE '[ERRO]   %  -> deveria ser aceito: %', rotulo, SQLERRM;
        END IF;
    END;
END;
$$;

-- "Aceito" que a regra de negócio proíbe = brecha (o comando é desfeito no fim)
CREATE OR REPLACE FUNCTION pg_temp.brecha_se_aceitar(rotulo text, comando text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE comando;
        RAISE NOTICE '[BRECHA] %  -> o banco ACEITOU', rotulo;
        RAISE EXCEPTION 'desfazer';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'desfazer' THEN
            RAISE NOTICE '[OK]     %  -> recusado: %', rotulo, SQLERRM;
        END IF;
    END;
END;
$$;

\echo
\echo '=== 0. Os dados fictícios respeitam o schema ==='
SELECT 'chaves com mais de 1 empréstimo ativo' AS verificacao, count(*) AS problemas
  FROM (SELECT key_id FROM keys_keyloan WHERE returned_at IS NULL GROUP BY key_id HAVING count(*) > 1) x
UNION ALL
SELECT 'empréstimos sem movimento de retirada', count(*)
  FROM keys_keyloan l WHERE NOT EXISTS (SELECT 1 FROM keys_keymovement m WHERE m.loan_id = l.id AND m.kind = 'checkout')
UNION ALL
SELECT 'devolvidos sem movimento de devolução', count(*)
  FROM keys_keyloan l WHERE l.returned_at IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM keys_keymovement m WHERE m.loan_id = l.id AND m.kind = 'return')
UNION ALL
SELECT 'movimentos com horário/operador diferente do empréstimo', count(*)
  FROM keys_keymovement m JOIN keys_keyloan l ON l.id = m.loan_id
 WHERE (m.kind = 'checkout' AND (m.occurred_at <> l.checked_out_at OR m.operator_id <> l.checkout_operator_id))
    OR (m.kind = 'return' AND (m.occurred_at IS DISTINCT FROM l.returned_at OR m.operator_id IS DISTINCT FROM l.return_operator_id))
UNION ALL
SELECT 'reservas ativas sobrepostas no mesmo espaço', count(*)
  FROM bookings_booking a JOIN bookings_booking b
    ON a.space_id = b.space_id AND a.id < b.id AND a.status = 'active' AND b.status = 'active'
   AND tstzrange(a.start_at, a.end_at, '[)') && tstzrange(b.start_at, b.end_at, '[)');

\echo
\echo '=== 1. Uma sala possui várias chaves ==='
SELECT s.code AS espaco, count(k.id) AS chaves FROM spaces_space s
  LEFT JOIN keys_key k ON k.space_id = s.id GROUP BY s.code ORDER BY s.code;
SELECT pg_temp.deve_passar('cadastrar 3ª chave para LAB-01',
    $q$INSERT INTO keys_key (space_id) VALUES ((SELECT id FROM spaces_space WHERE code = 'LAB-01'))$q$);
SELECT pg_temp.deve_falhar('chave apontando para espaço inexistente',
    $q$INSERT INTO keys_key (space_id) VALUES (999999); SET CONSTRAINTS ALL IMMEDIATE$q$);
SELECT pg_temp.deve_falhar('apagar espaço que tem chaves (PROTECT)',
    $q$DELETE FROM spaces_space WHERE code = 'LAB-01'; SET CONSTRAINTS ALL IMMEDIATE$q$);
SELECT pg_temp.deve_falhar('mudar de espaço uma chave com histórico (trigger)',
    $q$UPDATE keys_key SET space_id = (SELECT id FROM spaces_space WHERE code = 'SALA-101')
       WHERE id = (SELECT key_id FROM keys_keyloan ORDER BY id LIMIT 1)$q$);

\echo
\echo '=== 2. Uma chave não possui dois empréstimos ativos ==='
SELECT pg_temp.deve_falhar('2º empréstimo ativo da mesma chave',
    $q$INSERT INTO keys_keyloan (checked_out_at, checkout_operator_id, key_id, responsible_id)
       SELECT now(), checkout_operator_id, key_id, responsible_id FROM keys_keyloan WHERE returned_at IS NULL LIMIT 1$q$);
SELECT pg_temp.deve_passar('novo empréstimo de uma chave já devolvida',
    $q$INSERT INTO keys_keyloan (checked_out_at, checkout_operator_id, key_id, responsible_id)
       SELECT now(), 1, k.id, 8 FROM keys_key k
        WHERE NOT EXISTS (SELECT 1 FROM keys_keyloan l WHERE l.key_id = k.id AND l.returned_at IS NULL) LIMIT 1$q$);

\echo
\echo '=== 3. Uma devolução pertence a uma retirada existente ==='
SELECT pg_temp.deve_falhar('devolução antes da retirada',
    $q$UPDATE keys_keyloan SET returned_at = checked_out_at - interval '1 minute', return_operator_id = 1
       WHERE id = (SELECT id FROM keys_keyloan WHERE returned_at IS NULL LIMIT 1)$q$);
SELECT pg_temp.deve_falhar('devolução sem operador que recebeu',
    $q$UPDATE keys_keyloan SET returned_at = now()
       WHERE id = (SELECT id FROM keys_keyloan WHERE returned_at IS NULL LIMIT 1)$q$);
SELECT pg_temp.deve_falhar('2ª devolução do mesmo empréstimo (UNIQUE loan_id, kind)',
    $q$INSERT INTO keys_keymovement (kind, occurred_at, loan_id, operator_id)
       SELECT 'return', now(), loan_id, operator_id FROM keys_keymovement WHERE kind = 'return' LIMIT 1$q$);
SELECT pg_temp.deve_falhar('movimento de devolução para empréstimo inexistente',
    $q$INSERT INTO keys_keymovement (kind, occurred_at, loan_id, operator_id) VALUES ('return', now(), 999999, 1);
       SET CONSTRAINTS ALL IMMEDIATE$q$);
SELECT pg_temp.brecha_se_aceitar('movimento de DEVOLUÇÃO num empréstimo ainda ATIVO',
    $q$INSERT INTO keys_keymovement (kind, occurred_at, loan_id, operator_id)
       SELECT 'return', now(), id, 1 FROM keys_keyloan WHERE returned_at IS NULL LIMIT 1$q$);
SELECT pg_temp.brecha_se_aceitar('empréstimo DEVOLVIDO sem nenhum movimento',
    $q$INSERT INTO keys_keyloan (checked_out_at, returned_at, checkout_operator_id, return_operator_id, key_id, responsible_id)
       VALUES (now() - interval '2 hours', now() - interval '1 hour', 1, 1,
               (SELECT id FROM keys_key ORDER BY id DESC LIMIT 1), 8);
       SET CONSTRAINTS ALL IMMEDIATE$q$);
SELECT pg_temp.brecha_se_aceitar('movimento com horário diferente do empréstimo',
    $q$INSERT INTO keys_keymovement (kind, occurred_at, loan_id, operator_id)
       SELECT 'return', checked_out_at - interval '3 days', id, 2 FROM keys_keyloan WHERE returned_at IS NULL LIMIT 1$q$);

\echo
\echo '=== 4. O histórico de movimentações é preservado ==='
SELECT pg_temp.deve_falhar('alterar movimentação existente (trigger)',
    $q$UPDATE keys_keymovement SET occurred_at = now() WHERE id = 1$q$);
SELECT pg_temp.deve_falhar('apagar movimentação existente (trigger)',
    $q$DELETE FROM keys_keymovement WHERE id = 1$q$);
SELECT pg_temp.deve_falhar('apagar empréstimo que tem movimentos (PROTECT)',
    $q$DELETE FROM keys_keyloan WHERE id = 1; SET CONSTRAINTS ALL IMMEDIATE$q$);
SELECT pg_temp.deve_falhar('apagar usuário com histórico (PROTECT)',
    $q$DELETE FROM auth_user WHERE id = (SELECT responsible_id FROM keys_keyloan LIMIT 1); SET CONSTRAINTS ALL IMMEDIATE$q$);
SELECT pg_temp.brecha_se_aceitar('reescrever o RESPONSÁVEL de um empréstimo já encerrado',
    $q$UPDATE keys_keyloan SET responsible_id = 9 WHERE id = 1$q$);
SELECT pg_temp.brecha_se_aceitar('reescrever o HORÁRIO de retirada de um empréstimo encerrado',
    $q$UPDATE keys_keyloan SET checked_out_at = checked_out_at - interval '1 day' WHERE id = 1$q$);
SELECT pg_temp.brecha_se_aceitar('"desfazer" uma devolução (returned_at volta a NULL)',
    $q$UPDATE keys_keyloan SET returned_at = NULL, return_operator_id = NULL
       WHERE id = (SELECT l.id FROM keys_keyloan l WHERE l.returned_at IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM keys_keyloan a WHERE a.key_id = l.key_id AND a.returned_at IS NULL)
                  ORDER BY l.id DESC LIMIT 1)$q$);

\echo
\echo '=== 5. Duas reservas não ocupam o mesmo espaço em horários sobrepostos ==='
SELECT pg_temp.deve_falhar('reserva ativa sobreposta (10:30–11:30 no LAB-01, 24/11)',
    $q$INSERT INTO bookings_booking (start_at, end_at, status, created_at, space_id, user_id)
       VALUES ('2026-11-24 10:30-03', '2026-11-24 11:30-03', 'active', now(),
               (SELECT id FROM spaces_space WHERE code = 'LAB-01'), 5)$q$);
SELECT pg_temp.deve_passar('reserva encostada (12:00–13:00 logo após 11:00–12:00)',
    $q$INSERT INTO bookings_booking (start_at, end_at, status, created_at, space_id, user_id)
       VALUES ('2026-11-24 12:00-03', '2026-11-24 13:00-03', 'active', now(),
               (SELECT id FROM spaces_space WHERE code = 'LAB-01'), 5)$q$);
SELECT pg_temp.deve_passar('mesmo horário em OUTRO espaço',
    $q$INSERT INTO bookings_booking (start_at, end_at, status, created_at, space_id, user_id)
       VALUES ('2026-11-24 10:30-03', '2026-11-24 11:30-03', 'active', now(),
               (SELECT id FROM spaces_space WHERE code = 'LAB-02'), 5)
       ON CONFLICT DO NOTHING$q$);
SELECT pg_temp.deve_falhar('reaTIVAR reserva cancelada que conflita',
    $q$UPDATE bookings_booking SET status = 'active', cancelled_at = NULL
       WHERE status = 'cancelled' AND space_id = (SELECT id FROM spaces_space WHERE code = 'LAB-01')
         AND start_at = '2026-11-24 10:30-03'$q$);
SELECT pg_temp.deve_falhar('reserva com fim antes do início',
    $q$INSERT INTO bookings_booking (start_at, end_at, status, created_at, space_id, user_id)
       VALUES ('2026-11-25 12:00-03', '2026-11-25 11:00-03', 'active', now(), 1, 5)$q$);
SELECT pg_temp.deve_falhar('reserva cancelada sem data de cancelamento',
    $q$INSERT INTO bookings_booking (start_at, end_at, status, created_at, space_id, user_id)
       VALUES ('2026-11-26 08:00-03', '2026-11-26 09:00-03', 'cancelled', now(), 1, 5)$q$);
SELECT pg_temp.brecha_se_aceitar('cancelamento registrado ANTES da criação da reserva',
    $q$INSERT INTO bookings_booking (start_at, end_at, status, created_at, cancelled_at, space_id, user_id)
       VALUES ('2026-11-27 08:00-03', '2026-11-27 09:00-03', 'cancelled', now(), now() - interval '10 days', 1, 5)$q$);

\echo
\echo '=== 6. Outras verificações ==='
SELECT pg_temp.deve_falhar('código de espaço só com espaços', $q$INSERT INTO spaces_space (code, kind) VALUES ('   ', 'room')$q$);
SELECT pg_temp.deve_falhar('tipo de espaço inválido', $q$INSERT INTO spaces_space (code, kind) VALUES ('X-1', 'garage')$q$);
SELECT pg_temp.brecha_se_aceitar('código duplicado só mudando maiúsculas (LAB-01 x lab-01)',
    $q$INSERT INTO spaces_space (code, kind) VALUES ('lab-01', 'laboratory')$q$);
SELECT pg_temp.brecha_se_aceitar('código duplicado com espaços nas pontas (" LAB-01 ")',
    $q$INSERT INTO spaces_space (code, kind) VALUES (' LAB-01 ', 'laboratory')$q$);
SELECT pg_temp.brecha_se_aceitar('usuário INATIVO como responsável de empréstimo',
    $q$UPDATE auth_user SET is_active = FALSE WHERE id = 12;
       INSERT INTO keys_keyloan (checked_out_at, checkout_operator_id, key_id, responsible_id)
       SELECT now(), 1, k.id, 12 FROM keys_key k
        WHERE NOT EXISTS (SELECT 1 FROM keys_keyloan l WHERE l.key_id = k.id AND l.returned_at IS NULL) LIMIT 1$q$);
SELECT pg_temp.brecha_se_aceitar('operador que NÃO é staff registrando retirada (a API já barra com IsAdminUser)',
    $q$INSERT INTO keys_keyloan (checked_out_at, checkout_operator_id, key_id, responsible_id)
       SELECT now(), 10, k.id, 8 FROM keys_key k
        WHERE NOT EXISTS (SELECT 1 FROM keys_keyloan l WHERE l.key_id = k.id AND l.returned_at IS NULL) LIMIT 1$q$);
SELECT pg_temp.brecha_se_aceitar('retirada com data no FUTURO',
    $q$INSERT INTO keys_keyloan (checked_out_at, checkout_operator_id, key_id, responsible_id)
       SELECT now() + interval '30 days', 1, k.id, 8 FROM keys_key k
        WHERE NOT EXISTS (SELECT 1 FROM keys_keyloan l WHERE l.key_id = k.id AND l.returned_at IS NULL) LIMIT 1$q$);

\echo
\echo 'Fim. Nenhum dado foi alterado (todos os testes foram desfeitos).'
