# LabTech: dicionário de dados

**Fonte:** repositório `squad-1-UDF/back-end`, branch `main`, commit `ee65ad3` (19/11/2026), migrations `spaces/0001`, `keys/0001` e `bookings/0001`, além do `auth.User` do Django.
**Banco:** PostgreSQL 16. Todas as datas são `timestamptz`, gravadas em UTC (`USE_TZ=True`).
**Diagrama:** `diagrama/DER-LabTech.drawio` (editável) e `diagrama/DER-LabTech.png`.

## Situação de cada parte

| Situação | O que entra | Como aparece no DER |
|---|---|---|
| ✅ **Implementado** | `auth_user` (UC001/UC002) e `spaces_space` (UC003). Têm API e testes, e o contrato está fechado. | Borda contínua |
| 🟡 **Em desenvolvimento** | `keys_key`, `keys_keyloan`, `keys_keymovement` (UC004–UC008) e `bookings_booking` (reservas). As migrations já estão no `main` desde 19/11, mas nomes, campos e permissões ainda são **contrato provisório** (`docs/REQUISITOS_E_CONTRATO.md`). | Borda tracejada, com selo "EM DESENVOLVIMENTO" |
| 💡 **Proposta** | Campos novos sugeridos pelo squad de dados. **Não existem no código.** | Linha em itálico, marcada com `+` |

Legenda das colunas das tabelas abaixo: **PK** chave primária · **FK** chave estrangeira · **UQ** valor único · **CK** regra CHECK · **NN** obrigatório (NOT NULL).

---

## 1. `auth_user`: Usuários ✅ Implementado

Usuário nativo do Django, adotado provisoriamente. Representa ao mesmo tempo quem **retira** a chave (o responsável), quem **registra** a operação no balcão (o operador, com `is_staff`) e quem **reserva** um espaço.

| Coluna | Tipo | Chave | NN | Significado |
|---|---|---|---|---|
| `id` | `integer` (identity) | PK | ✔ | Identificador do usuário. É `integer`, diferente das outras tabelas, que usam `bigint`. |
| `username` | `varchar(150)` | UQ | ✔ | Login. |
| `password` | `varchar(128)` | | ✔ | Hash da senha (nunca a senha em texto). |
| `first_name` / `last_name` | `varchar(150)` | | ✔ | Nome e sobrenome (podem ficar vazios). |
| `email` | `varchar(254)` | | ✔ | E-mail. Pode ficar vazio e **não é único**. |
| `is_staff` | `boolean` | | ✔ | Pode operar o balcão e administrar. A API usa esse campo para liberar cadastro de espaços, retirada e devolução. |
| `is_active` | `boolean` | | ✔ | Conta ativa. Desativar no lugar de apagar preserva o histórico. |
| `is_superuser` | `boolean` | | ✔ | Acesso total. |
| `last_login` | `timestamptz` | | | Último login. |
| `date_joined` | `timestamptz` | | ✔ | Data do cadastro. |

## 2. `spaces_space`: Salas e laboratórios ✅ Implementado

| Coluna | Tipo | Chave | NN | Significado |
|---|---|---|---|---|
| `id` | `bigint` (identity) | PK | ✔ | Identificador do espaço. |
| `code` | `varchar(50)` | UQ, CK | ✔ | Código de identificação (ex.: `LAB-01`, `SALA-101`). Precisa ter ao menos um caractere que não seja espaço (`spaces_space_code_nonblank`). |
| `kind` | `varchar(10)` | CK | ✔ | Tipo do espaço: `room` (sala) ou `laboratory` (laboratório). Regra `spaces_space_kind_valid`. |
| `name` | `varchar(100)` | 💡 | | **Proposta:** nome de exibição (ex.: "Laboratório de Redes"). |
| `location` | `varchar(120)` | 💡 | | **Proposta:** bloco e andar. |
| `capacity` | `integer` | 💡 CK > 0 | | **Proposta:** capacidade de pessoas. |
| `is_active` | `boolean` | 💡 | | **Proposta:** espaço ativo ou desativado, para não precisar apagar. |

Relacionamentos: **1 espaço → N chaves** e **1 espaço → N reservas**, ambos com `PROTECT`, ou seja, um espaço que tem chave ou reserva não pode ser apagado.

## 3. `keys_key`: Chaves 🟡 Em desenvolvimento

| Coluna | Tipo | Chave | NN | Significado |
|---|---|---|---|---|
| `id` | `bigint` (identity) | PK | ✔ | Identificador da chave. Hoje **é a única identificação da chave**. |
| `space_id` | `bigint` | FK → `spaces_space.id` | ✔ | Espaço que a chave abre. Uma sala pode ter várias chaves (cópias). |
| `label` | `varchar(30)` | 💡 UQ | | **Proposta:** etiqueta física (ex.: `LAB-01-A`) para o balcão identificar a chave. |
| `status` | `varchar(12)` | 💡 CK | | **Proposta:** `available`, `maintenance` ou `lost`, para indisponibilidade física ou administrativa (os docs do back-end citam que isso ainda não existe). |

Regras:
- `PROTECT` para o espaço.
- O trigger **`keys_key_space_fixed_after_loan`** impede mudar o `space_id` de uma chave que já tem empréstimo.

## 4. `keys_keyloan`: Empréstimos de chaves 🟡 Em desenvolvimento

Uma linha por retirada. A devolução preenche `returned_at` e `return_operator_id` na mesma linha.

| Coluna | Tipo | Chave | NN | Significado |
|---|---|---|---|---|
| `id` | `bigint` (identity) | PK | ✔ | Identificador do empréstimo. |
| `key_id` | `bigint` | FK → `keys_key.id`, UQ parcial | ✔ | Chave emprestada. |
| `responsible_id` | `integer` | FK → `auth_user.id` | ✔ | Pessoa que retirou e responde pela chave. |
| `checkout_operator_id` | `integer` | FK → `auth_user.id` | ✔ | Funcionário que registrou a retirada. |
| `checked_out_at` | `timestamptz` | | ✔ | Data e hora da retirada. |
| `returned_at` | `timestamptz` | CK | | Data e hora da devolução. Vazio significa **empréstimo ativo**. |
| `return_operator_id` | `integer` | FK → `auth_user.id`, CK | | Funcionário que recebeu a chave de volta. |
| `expected_return_at` | `timestamptz` | 💡 | | **Proposta:** prazo de devolução, para identificar atrasos. |

Regras:
- **`keys_one_active_loan_per_key`** (UNIQUE parcial `key_id WHERE returned_at IS NULL`): uma chave não tem dois empréstimos ativos.
- **`keys_return_not_before_checkout`** (CHECK): a devolução não pode ser antes da retirada.
- **`keys_return_time_operator_together`** (CHECK): `returned_at` e `return_operator_id` ficam os dois preenchidos ou os dois vazios.
- `PROTECT` em todas as FKs.

## 5. `keys_keymovement`: Movimentações de retirada e devolução 🟡 Em desenvolvimento

Trilha de auditoria. Cada empréstimo gera um movimento `checkout` e, quando devolvido, um movimento `return`.

| Coluna | Tipo | Chave | NN | Significado |
|---|---|---|---|---|
| `id` | `bigint` (identity) | PK | ✔ | Identificador do movimento. |
| `loan_id` | `bigint` | FK → `keys_keyloan.id`, UQ (com `kind`) | ✔ | Empréstimo a que o movimento pertence. |
| `kind` | `varchar(8)` | CK, UQ (com `loan_id`) | ✔ | `checkout` (retirada) ou `return` (devolução). |
| `occurred_at` | `timestamptz` | | ✔ | Quando aconteceu. |
| `operator_id` | `integer` | FK → `auth_user.id` | ✔ | Funcionário que registrou. |

Regras:
- **`keys_movement_kind_valid`** (CHECK): o tipo precisa ser `checkout` ou `return`.
- **`keys_one_movement_per_loan_kind`** (UNIQUE `loan_id, kind`): no máximo 1 retirada e 1 devolução por empréstimo.
- O trigger **`keys_movement_immutable`** recusa qualquer `UPDATE` ou `DELETE`, então o histórico não é alterado nem por SQL direto.

## 6. `bookings_booking`: Reservas de salas 🟡 Em desenvolvimento

| Coluna | Tipo | Chave | NN | Significado |
|---|---|---|---|---|
| `id` | `bigint` (identity) | PK | ✔ | Identificador da reserva. |
| `space_id` | `bigint` | FK → `spaces_space.id` | ✔ | Espaço reservado. |
| `user_id` | `integer` | FK → `auth_user.id` | ✔ | Quem reservou. |
| `start_at` | `timestamptz` | CK | ✔ | Início (incluído no intervalo). |
| `end_at` | `timestamptz` | CK | ✔ | Fim (não incluído): o intervalo é **[início, fim)**. |
| `status` | `varchar(9)` | CK | ✔ | `active` (ativa) ou `cancelled` (cancelada). O padrão `active` vem do Django, não do banco. |
| `created_at` | `timestamptz` | | ✔ | Quando a reserva foi criada. |
| `cancelled_at` | `timestamptz` | CK | | Quando foi cancelada. |

Regras:
- **`bookings_start_before_end`** (CHECK): `start_at < end_at`.
- **`bookings_status_valid`** (CHECK): o status precisa ser um dos valores permitidos.
- **`bookings_cancelled_at_matches_status`** (CHECK): uma reserva ativa não tem `cancelled_at` e uma cancelada tem.
- **`bookings_active_no_overlap`** (EXCLUDE com GiST e a extensão `btree_gist`): duas reservas **ativas** do mesmo espaço não podem ter horários sobrepostos. Reservas encostadas, como 10h–11h e 11h–12h, são permitidas. Uma reserva cancelada não bloqueia horário.

---

## Relacionamentos (todos com `ON DELETE PROTECT`)

| De | Para | Cardinalidade | Observação |
|---|---|---|---|
| `spaces_space` | `keys_key` | 1 : N | Uma sala pode ter várias chaves ou nenhuma. |
| `spaces_space` | `bookings_booking` | 1 : N | |
| `keys_key` | `keys_keyloan` | 1 : N | No máximo 1 empréstimo ativo por chave. |
| `keys_keyloan` | `keys_keymovement` | 1 : 0..2 | Esperado: 1 retirada + 1 devolução (se devolvido). O banco hoje não exige a existência (ver B2). |
| `auth_user` | `keys_keyloan` | 1 : N (×3) | Como responsável, operador da retirada e operador da devolução (opcional). |
| `auth_user` | `keys_keymovement` | 1 : N | Como operador. |
| `auth_user` | `bookings_booking` | 1 : N | Como quem reservou. |

## Arquivos relacionados

- `sql/schema-labtech.sql`: DDL atual reconstruído das migrations, para documentação e testes locais.
- `sql/validacao-integridade.sql`: testa cada regra num banco local, sem alterar nada.
- `sql/propostas-integridade.sql`: sugestões que fecham as brechas encontradas (não aplicadas no back-end).
- `inconsistencias-e-sugestoes.md`: resultado da revisão.
- `dados/`: base fictícia em CSV e JSON.
