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

## Contrato de API sugerido — não implementado

`/api/v1/` é a versão inicial. Recursos previstos:

| Área | Exemplo de endpoint | Ação esperada |
|---|---|---|
| Autenticação | `POST /auth/login/` | Autenticar (mecanismo a decidir) |
| Usuários | `/users/` | Operações restritas por papel |
| Salas | `/spaces/` | Listar e manter salas/laboratórios |
| Chaves | `/keys/` | Manter e consultar disponibilidade |
| Retiradas | `/key-loans/` | Entregar/devolver com registro auditável |
| Reservas | `/bookings/` | Reservar, listar e cancelar |
| Agenda | `/availability/` | Verificar horários sem conflitos |

Endpoints, nomes e campos são **propostas**, não contratos aprovados. As operações de reserva devem validar conflitos em transação no banco, depois que o esquema for acordado.

## Alinhamento necessário com responsável pelo banco

- Nomes das tabelas e colunas, tipos e nulabilidade.
- PK/FK, índices e constraints (unicidade, reservas conflitantes, exclusão ou desativação).
- Identidades e permissões: usar `auth_user` nativo Django ou tabela de usuários preexistente? Resolver antes da primeira migration de autenticação.
- Quem produz e aplica migrations, inclusive as apps nativas do Django.
- Convenções de timestamps e timezone.
- Estratégia de ambientes (development/test) e criação de bancos de teste.

Nenhum model de negócio foi criado nesta fase para evitar divergência com o trabalho de modelagem.
