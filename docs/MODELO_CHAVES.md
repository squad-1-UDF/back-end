# Persistência de chaves e empréstimos (UC004–UC008)

`keys.0001_initial` cria `Key`, `KeyLoan` e `KeyMovement` no PostgreSQL; `keys.0002_integridade` acrescenta as regras de integridade propostas pelo squad de dados (veja abaixo). Depende somente de `spaces.0001_initial` e de `settings.AUTH_USER_MODEL`; não importa dados ou migrations do projeto de chatbot.

| Entidade | Campos e relações |
|---|---|
| `Key` | `id` BigAutoField; `space_id` FK para `Space` com `PROTECT`. A identificação da chave é sua PK. |
| `KeyLoan` | `id`; FKs distintas para chave, usuário responsável cadastrado, operador de retirada e operador opcional de devolução; `checked_out_at` e `returned_at` opcionais na devolução. |
| `KeyMovement` | `id`; FK para empréstimo; `kind` (`checkout` ou `return`); `occurred_at`; FK para operador. |

O banco impõe `UNIQUE (key_id) WHERE returned_at IS NULL`, `CHECK (returned_at IS NULL OR returned_at >= checked_out_at)`, `CHECK` que exige horário e operador de devolução juntos, `CHECK` do tipo de movimento e unicidade de `(loan_id, kind)`. Triggers da migration impedem mudar `space_id` de chave com histórico de empréstimo e fazer UPDATE ou DELETE de movimentações existentes, inclusive por SQL direto. Ambos têm SQL reverso. Os horários são `timestamptz` com `USE_TZ=True`; os serviços exigem `datetime` com timezone pelas regras puras. FKs usam `PROTECT` para preservar referências históricas.

`apps.keys.services.checkout_key` e `return_key` bloqueiam a linha da chave, usam as regras existentes e gravam empréstimo e movimento na mesma transação. Ao reler o histórico, conferem horário e operador dos movimentos contra o empréstimo e exigem retirada para todo empréstimo e devolução para todo empréstimo encerrado. `movements_for_key` ordena por horário e ID. `has_active_loan` informa somente ausência/presença de empréstimo ativo, sem representar disponibilidade física ou administrativa. Os serviços continuam conferindo o histórico ao relê-lo, o que também protege dados gravados antes de `keys.0002_integridade`.

`keys.0002_integridade` (propostas P1–P5 de `docs/dados/sql/propostas-integridade.sql`) passa a impor no banco, inclusive para SQL direto:

| Regra | Objeto | Brecha fechada |
|---|---|---|
| Dados da retirada (chave, responsável, operador, horário) não mudam; devolução registrada não é alterada nem desfeita | trigger `keys_loan_guard_update` (`keys_loan_checkout_immutable`, `keys_loan_return_immutable`) | B4, B5 |
| Movimento de retirada bate com horário e operador do empréstimo; movimento de devolução exige devolução registrada com mesmo horário e operador | trigger `keys_movement_matches_loan` | B1, B3 |
| Todo empréstimo tem movimento de retirada e, se devolvido, de devolução | constraint trigger `keys_loan_requires_movements`, `DEFERRABLE INITIALLY DEFERRED` (conferido no COMMIT) | B2 |
| Retirada não pode estar no futuro (tolerância de 5 minutos) | trigger `keys_loan_not_in_future` | B10 |
| Responsável precisa estar ativo na retirada | trigger `keys_loan_responsible_active` | B9 |

Todas têm SQL reverso. A ordem de gravação de `checkout_key` e `return_key` (empréstimo, depois movimento) é compatível com elas. Como o trigger de P3 é adiado, testes que precisam vê-lo disparar usam `pytest.mark.django_db(transaction=True)` (`apps/tests/test_integridade_postgres.py`). "Operador precisa ser staff" (B11) continua garantido só na API.

O responsável e os operadores usam provisoriamente `auth.User`, por FKs distintas. Responsáveis externos sem conta exigirão cadastro separado numa evolução futura. A retirada e a devolução têm endpoints HTTP (`POST /api/v1/key-loans/` e `POST /api/v1/key-loans/{loan_id}/return/`), restritos a staff (`IsAdminUser`) com CSRF; as consultas `GET /api/v1/keys/{key_id}/loan-availability/` e `GET /api/v1/keys/{key_id}/movements/` exigem sessão autenticada (veja `GUIA_FRONTEND_MVP.md`). O cadastro e a edição de chaves por HTTP ainda não existem.

Os testes integrados usam somente o PostgreSQL local isolado (`test_labtech_local`) ou o efêmero da CI (`test_labtech_ci`), criados pelo pytest-django. A migration não deve ser aplicada em banco compartilhado ou de produção sem autorização.
