# Persistência de chaves e empréstimos (UC004–UC008)

`keys.0001_initial` cria `Key`, `KeyLoan` e `KeyMovement` no PostgreSQL. Depende somente de `spaces.0001_initial` e de `settings.AUTH_USER_MODEL`; não importa dados ou migrations do projeto de chatbot.

| Entidade | Campos e relações |
|---|---|
| `Key` | `id` BigAutoField; `space_id` FK para `Space` com `PROTECT`. A identificação da chave é sua PK. |
| `KeyLoan` | `id`; FKs distintas para chave, usuário responsável cadastrado, operador de retirada e operador opcional de devolução; `checked_out_at` e `returned_at` opcionais na devolução. |
| `KeyMovement` | `id`; FK para empréstimo; `kind` (`checkout` ou `return`); `occurred_at`; FK para operador. |

O banco impõe `UNIQUE (key_id) WHERE returned_at IS NULL`, `CHECK (returned_at IS NULL OR returned_at >= checked_out_at)`, `CHECK` que exige horário e operador de devolução juntos, `CHECK` do tipo de movimento e unicidade de `(loan_id, kind)`. Triggers da migration impedem mudar `space_id` de chave com histórico de empréstimo e fazer UPDATE ou DELETE de movimentações existentes, inclusive por SQL direto. Ambos têm SQL reverso. Os horários são `timestamptz` com `USE_TZ=True`; os serviços exigem `datetime` com timezone pelas regras puras. FKs usam `PROTECT` para preservar referências históricas.

`apps.keys.services.checkout_key` e `return_key` bloqueiam a linha da chave, usam as regras existentes e gravam empréstimo e movimento na mesma transação. Ao reler o histórico, conferem horário e operador dos movimentos contra o empréstimo e exigem retirada para todo empréstimo e devolução para todo empréstimo encerrado. `movements_for_key` ordena por horário e ID. `has_active_loan` informa somente ausência/presença de empréstimo ativo, sem representar disponibilidade física ou administrativa. **O banco não exige a presença de todos os eventos nem a correspondência de horário e operador com o empréstimo.** Escritas diretas em `KeyLoan` ou inserções diretas em `KeyMovement` ainda podem criar inconsistências; os serviços detectam essas situações ao reler o histórico.

O responsável e os operadores usam provisoriamente `auth.User`, por FKs distintas. Responsáveis externos sem conta exigirão cadastro separado numa evolução futura. Não há endpoints HTTP ou permissões administrativas nesta etapa. A PR #8 usa `space_id` textual em seu serializer provisório; a integração futura precisará adaptá-lo ao `Space.id` inteiro.

Os testes integrados usam somente o PostgreSQL local isolado (`test_labtech_local`) ou o efêmero da CI (`test_labtech_ci`), criados pelo pytest-django. A migration não deve ser aplicada em banco compartilhado ou de produção sem autorização.
