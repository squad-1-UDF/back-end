# LabTech: entrega do squad de dados

> **Autoria e crédito:** material produzido por **Luís Felipe** (squad de dados, Squad 1 – UDF) e copiado para o repositório do back-end como referência. O conteúdo original foi preservado; só esta nota foi acrescentada.
>
> **Situação no back-end:** as propostas P1–P7 de `sql/propostas-integridade.sql` foram aplicadas pelas migrations `spaces/0002_integridade` (P7), `keys/0002_integridade` (P1–P5) e `bookings/0002_integridade` (P6), com testes em `apps/tests/test_integridade_postgres.py`. As inconsistências de documentação I9 e I10 foram corrigidas em `docs/MODELO_CHAVES.md` e `docs/REQUISITOS_E_CONTRATO.md`. O texto abaixo descreve o estado do `main` em `ee65ad3`, antes dessas mudanças.
>
> **Arquivos não copiados:** `Entrega LabTech - Squad de Dados.docx` e `.pdf` (documento consolidado da entrega) e `diagrama/DER-LabTech.svg` (cerca de 2,9 MB); o DER segue disponível em `diagrama/DER-LabTech.drawio` e `diagrama/DER-LabTech.png`. A pasta `dados/csv/` não fazia parte do material recebido; ela é gerada por `dados/gerar_dados.py`. Os scripts desta pasta ficam fora do `ruff` do projeto (`extend-exclude` no `pyproject.toml`) para manter o material como entregue.

Modelagem, documentação e validação do banco do LabTech (`squad-1-UDF/back-end`, `main` @ `ee65ad3`).
Nada aqui altera o back-end: não há models, migrations nem comandos no banco compartilhado.

## Entregáveis

| Pedido | Arquivo |
|---|---|
| 1. DER atualizado (editável) | `diagrama/DER-LabTech.drawio` (abre em app.diagrams.net), `diagrama/DER-LabTech.png`, `diagrama/DER-LabTech.svg` |
| 2. Dicionário de dados | `dicionario-de-dados.md` |
| 3. Dados fictícios para demonstração | `dados/csv/*.csv`, `dados/labtech-demo.json`, `dados/fixture-django.json`, `sql/dados-demo.sql` |
| 4. Revisão de integridade, inconsistências e sugestões | `inconsistencias-e-sugestoes.md`, `sql/validacao-integridade.sql`, `sql/propostas-integridade.sql` |

## Situação das entidades

- ✅ **Implementado:** Usuários (`auth.User`) e Salas/laboratórios (`Space`).
- 🟡 **Em desenvolvimento:** Chaves (`Key`), Empréstimos (`KeyLoan`), Movimentações (`KeyMovement`) e Reservas (`Booking`). As migrations já estão no `main`, mas o contrato ainda é provisório.
- 💡 **Proposta:** campos sugeridos pelo squad de dados que não existem no código. No DER aparecem em itálico, marcados com `+`.

## Dados fictícios

São 12 usuários, 10 espaços, 13 chaves, 37 empréstimos (3 ativos), 71 movimentações e 32 reservas (4 canceladas). Os nomes são genéricos ("Professor Teste 1"), os e-mails usam `@exemplo.com` e as senhas são inutilizáveis, então ninguém consegue entrar com esses usuários. Todos os dados passam em todas as regras do banco.

A base inclui casos para a apresentação:
- reservas encostadas no `LAB-01` em 24/11, das 10h às 11h e das 11h às 12h, que são aceitas;
- uma reserva cancelada sobreposta no mesmo horário, que é aceita porque reserva cancelada não bloqueia;
- uma sala sem chave (`SALA-REUNIAO`).

Para gerar de novo: `python3 dados/gerar_dados.py`. O script usa só a biblioteca padrão e gera sempre o mesmo resultado.

Para carregar num banco local de teste (nunca no compartilhado):
- **SQL:** `psql -d <banco_local> -f sql/dados-demo.sql`, depois das migrations ou de `sql/schema-labtech.sql`.
- **Django:** `python manage.py loaddata caminho/para/fixture-django.json`, no banco local do Compose depois do `migrate`.

## Validação

```
createdb labtech_teste
psql -d labtech_teste -f sql/schema-labtech.sql
psql -d labtech_teste -f sql/dados-demo.sql
psql -d labtech_teste -f sql/validacao-integridade.sql     # 22 OK, 12 brechas
# para conferir as propostas, num banco novo: schema → propostas-integridade.sql → dados → validação  (33 OK, 1 brecha proposital)
```
