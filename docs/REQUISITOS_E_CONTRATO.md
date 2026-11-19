# Requisitos e contratos provisórios

## Com base na especificação recebida

- UC001: Fazer login (P1)
- UC002: Manter usuários (P1)
- UC003: Manter salas e laboratórios (P1)
- UC004: Manter chaves (P1)
- UC005: Registrar entrega de chave (P1)
- UC006: Registrar devolução de chave (P1)
- UC007: Consultar disponibilidade da chave (P2)
- UC008: Consultar histórico de movimentação (P2)
- UC009: Emitir histórico de chave (P3)

Regras principais: funções restritas exigem autenticação e permissões; salas têm identificação única; chaves pertencem a sala/laboratório; só se retira chave disponível; retirada associa usuário responsável e data/hora; devolução corresponde à retirada; histórico deve ser preservado; devolução torna chave disponível quando não houver outra restrição.

## Requisitos adicionais da proposta de MVP do grupo

Telas: login, dashboard, lista e detalhe de salas, agenda/disponibilidade, nova reserva, minhas reservas, administração. O texto menciona conflito de horário e cancelamento de reserva. **Esses pontos ainda precisam ser oficialmente incorporados aos requisitos escritos**.

## Contrato de API sugerido — implementação parcial de UC001 e UC003

`/api/v1/` é a versão inicial. Recursos previstos:

| Área | Exemplo de endpoint | Ação esperada |
|---|---|---|
| Autenticação | `GET /auth/csrf/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/me/` | Camada HTTP com sessões Django e cookie CSRF; `auth.User` nativo adotado provisoriamente, com PostgreSQL local e testes de integração separados |
| Usuários | `/users/` | Operações restritas por papel |
| Salas | `/spaces/` e `/spaces/{space_id}/` | Listar e consultar com sessão autenticada; cadastrar e atualizar parcialmente no PostgreSQL exigem provisoriamente `is_staff=True` e CSRF |
| Chaves | `/keys/` | Manter e consultar disponibilidade |
| Retiradas | `/key-loans/` | Entregar/devolver com registro auditável |
| Reservas | `/bookings/` | Reservar, listar e cancelar |
| Agenda | `/availability/` | Verificar horários sem conflitos |

Fora de UC001 e UC003, endpoints, nomes e campos são **propostas**, não contratos aprovados. Em UC001, `identifier`/`password`, sessões e respostas são provisórios. Em UC003, `id` é inteiro, `code` é único e `kind` aceita `room` ou `laboratory`; POST/PATCH exigem provisoriamente `is_staff=True`, enquanto a aprovação institucional final dessa política permanece pendente. As operações de reserva devem validar conflitos em transação no banco, depois que o esquema for acordado.

## Alinhamento necessário com responsável pelo banco

- Nomes das tabelas e colunas, tipos e nulabilidade.
- PK/FK, índices e constraints (unicidade, reservas conflitantes, exclusão ou desativação).
- Identidades e permissões: `auth_user` nativo foi adotado provisoriamente para UC001; fechar quem é responsável pela retirada e as permissões antes das migrations que referenciem pessoas.
- Definir quem produz e aplica as próximas migrations de domínio. As migrations nativas de autenticação/sessão e `spaces.0001_initial` são aplicadas apenas no PostgreSQL local isolado ou banco de teste nesta etapa.
- Convenções de timestamps e timezone.
- Estratégia de ambientes (development/test) e criação de bancos de teste.

O model mínimo `Space` de UC003 e suas quatro rotas HTTP usam PostgreSQL. Os demais models de negócio ainda dependem do contrato de dados.
