# LabTech: revisão de integridade, inconsistências e sugestões

Revisão do squad de dados sobre o `main` de `squad-1-UDF/back-end` (commit `ee65ad3`, 19/11/2026).
**Nenhum código, model ou migration do back-end foi alterado.** Tudo foi testado num PostgreSQL local descartável, com o schema reconstruído das migrations (`sql/schema-labtech.sql`) e a base fictícia (`dados/`).

Para repetir os testes:

```
createdb labtech_teste
psql -d labtech_teste -f sql/schema-labtech.sql
psql -d labtech_teste -f sql/dados-demo.sql
psql -d labtech_teste -f sql/validacao-integridade.sql
```

| Cenário | Testes OK | Brechas |
|---|---|---|
| Schema atual do `main` | **22** | **12** testes com brecha (11 brechas distintas: B4 tem 2 testes) |
| Schema atual + `sql/propostas-integridade.sql` | **33** | **1** (proposital: já é barrada na API) |

## 1. As 5 situações pedidas

| # | Situação | Resultado no banco atual | Como é garantida |
|---|---|---|---|
| 1 | Uma sala possui várias chaves | ✅ **Garantida** | FK `keys_key.space_id` sem unicidade: uma sala aceita N chaves. Nos dados de exemplo, os laboratórios têm 2 chaves e a `SALA-REUNIAO` tem 0. Não é possível apagar um espaço que tem chave (`PROTECT`), e uma chave com histórico não muda de sala (trigger). |
| 2 | Uma chave não possui dois empréstimos ativos | ✅ **Garantida** | `keys_one_active_loan_per_key` (UNIQUE parcial). Testado: o 2º empréstimo ativo é recusado, e um novo empréstimo depois da devolução é aceito. |
| 3 | Uma devolução pertence a uma retirada existente | ⚠️ **Parcial** | Garantido: a devolução não é antes da retirada, o operador é obrigatório, não existe 2ª devolução e o empréstimo precisa existir. **Brechas B1–B3** abaixo: o banco aceita um movimento de devolução num empréstimo ativo, um empréstimo devolvido sem movimentos e um movimento com horário diferente do empréstimo. |
| 4 | O histórico de movimentações é preservado | ⚠️ **Parcial** | Garantido: o trigger `keys_movement_immutable` bloqueia UPDATE e DELETE de movimentos, e `PROTECT` impede apagar empréstimo e usuário com histórico. **Brechas B4–B5**: a linha do **empréstimo** pode ser reescrita (responsável, horário) e a devolução pode ser "desfeita". |
| 5 | Duas reservas não ocupam o mesmo laboratório em horários sobrepostos | ✅ **Garantida** | `bookings_active_no_overlap` (EXCLUDE GiST, intervalo `[início, fim)`, só reservas ativas). Testado: sobreposição recusada, horários encostados aceitos, outro espaço aceito e reativar uma cancelada que conflita é recusado. |

## 2. Brechas encontradas (o banco aceita, mas a regra de negócio não permite)

Os serviços Python (`apps/keys/services.py`) não criam essas situações. O risco é gravação direta: SQL manual, admin, script de carga ou um bug futuro. O próprio `docs/MODELO_CHAVES.md` reconhece que "o banco não exige a presença de todos os eventos". As propostas estão em `sql/propostas-integridade.sql`, prontas para virar `RunSQL` numa migration, se o back-end aprovar.

| ID | Brecha (testada) | Gravidade | Proposta |
|---|---|---|---|
| B1 | Movimento de **devolução** num empréstimo que ainda está **ativo** | Alta | **P2**: trigger que confere se o movimento bate com o empréstimo |
| B2 | Empréstimo **devolvido sem nenhum movimento** (o histórico fica vazio) | Alta | **P3**: constraint trigger adiada (confere no COMMIT) que exige retirada e devolução |
| B3 | Movimento com **horário ou operador diferente** do empréstimo | Média | **P2** |
| B4 | Reescrever o **responsável** ou o **horário de retirada** de um empréstimo já encerrado | Alta | **P1**: trigger que congela os dados da retirada |
| B5 | **"Desfazer"** uma devolução (`returned_at` volta a vazio) | Alta | **P1** |
| B6 | Cancelamento registrado **antes da criação** da reserva | Baixa | **P6**: `CHECK (cancelled_at >= created_at)` |
| B7 | Código de espaço "duplicado" mudando só maiúsculas (`LAB-01` × `lab-01`) | Média | **P7**: índice único em `upper(btrim(code))` |
| B8 | Código duplicado com espaços nas pontas (`" LAB-01 "`) | Média | **P7** (hoje só o serializer da API remove os espaços) |
| B9 | Usuário **inativo** como responsável de empréstimo | Média | **P5**: trigger na retirada |
| B10 | Retirada com data no **futuro** | Baixa | **P4**: trigger com tolerância de 5 min |
| B11 | Operador **sem `is_staff`** registrando retirada | Baixa | Já é barrado na API (`IsAdminUser`). Deixar no banco é opcional, e a proposta não inclui |

A ordem de gravação dos serviços atuais (empréstimo e depois movimento) foi considerada: as propostas são compatíveis com `checkout_key` e `return_key` sem mudar o código Python.

## 3. Inconsistências de modelagem e documentação

| ID | Ponto | Sugestão |
|---|---|---|
| I1 | **A chave não tem identificação física.** A única identificação de `keys_key` é o `id`, então o balcão não tem como etiquetar "qual chave é qual". | Campo `label` único (proposta no DER). |
| I2 | **"Disponível" significa só "sem empréstimo ativo".** Não há como marcar uma chave perdida ou em manutenção (os próprios docs do back-end citam isso). | Campo `status` em `keys_key` (`available`, `maintenance`, `lost`) e regra "só empresta se `available`". |
| I3 | **Não há prazo de devolução**, então não dá para listar chaves atrasadas. | `expected_return_at` em `keys_keyloan` (proposta). |
| I4 | **Reserva e chave não se conversam.** Alguém pode retirar a chave de um laboratório reservado por outra pessoa naquele horário. | Definir a regra com o grupo, por exemplo: "retirada dentro de uma reserva ativa exige ser o dono da reserva ou staff". A validação fica no serviço. |
| I5 | **Responsável precisa ter conta** (`auth_user`). Visitante ou pessoa externa sem login não pode retirar. | Entidade futura de "responsável externo", já prevista nos docs do back-end como evolução. |
| I6 | **Perfis de usuário (UC002)** só existem como `is_staff`. Não há distinção entre professor, aluno e servidor. | Definir os papéis (grupo do Django ou tabela de perfil) antes de regras como "só professor reserva laboratório". |
| I7 | `auth_user.id` é `integer` e as outras tabelas usam `bigint`. | Sem problema prático; apenas registrar no contrato. |
| I8 | `auth_user.email` não é único e pode ficar vazio. | Se o e-mail virar login ou meio de aviso, tornar obrigatório e único. |
| I9 | `docs/MODELO_CHAVES.md` diz "Não há endpoints HTTP ou permissões administrativas nesta etapa", mas a PR #13 já criou `/key-loans/` com `IsAdminUser`. | Atualizar o documento. |
| I10 | `docs/REQUISITOS_E_CONTRATO.md` diz que "os demais models de negócio ainda dependem do contrato de dados", mas `keys` e `bookings` já têm migrations no `main`. | Alinhar o status: no DER, essas tabelas aparecem como **em desenvolvimento**, conforme pedido. |
| I11 | Reservas sem limites: não há duração máxima, horário de funcionamento nem antecedência mínima (`docs/REGRAS_RESERVAS.md` confirma). | Decisão do grupo. Se aprovadas, viram CHECKs ou regras de serviço. |
| I12 | `status` da reserva tem padrão `active` só no Django, não no banco. | Opcional: `db_default` para inserções diretas. |

## 4. Pontos fortes do modelo atual

- As regras críticas estão **no banco**, não só no Python: unicidade parcial, CHECKs, EXCLUDE e triggers.
- O uso de `PROTECT` em todas as FKs garante que nada é apagado em cascata.
- A reserva sem sobreposição usa `EXCLUDE ... USING gist`, que é a solução correta no PostgreSQL e funciona mesmo com requisições simultâneas.
- O histórico de movimentos é imutável por trigger.
- Os serviços usam `select_for_update` contra corrida em retiradas e reservas.
