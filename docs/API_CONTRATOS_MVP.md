# Proposta de contratos HTTP do LabTech

**Estado:** documento para discussão, sem implementação. A única rota existente nesta base é `GET /api/v1/health/`, que confirma somente que o processo HTTP responde. Nenhuma rota abaixo, exceto essa, existe no código. Consulte [requisitos e contrato inicial](REQUISITOS_E_CONTRATO.md).

## Origem e nível de certeza

| Origem | Conteúdo confirmado ou proposto |
|---|---|
| Requisitos UC001–UC009 | Login; manutenção de usuários, salas/laboratórios e chaves; entrega e devolução de chave; consulta de disponibilidade e histórico de chave; emissão de histórico (UC009, P3). Funções restritas exigem autenticação e permissões. Salas têm identificação única; chaves pertencem a um espaço; entrega exige chave disponível e registra responsável e data/hora; devolução corresponde à entrega; o histórico é preservado. |
| Proposta de MVP do grupo | Login, dashboard, salas, agenda, reservas, minhas reservas e administração. Conflito de horários e cancelamento de reserva **ainda não foram incorporados aos requisitos escritos**. |
| Regras puras integradas à main | [PR #2](https://github.com/squad-1-UDF/back-end/pull/2): intervalos de reserva `[início, fim)`, sem conflito quando consecutivos; filtro por espaço e estado ativo fica com o chamador. [PR #3](https://github.com/squad-1-UDF/back-end/pull/3): retirada/devolução e histórico de eventos. [PR #4](https://github.com/squad-1-UDF/back-end/pull/4): empréstimo ativo e movimentações por chave; ausência de empréstimo ativo não garante disponibilidade física ou administrativa. Essas PRs não são endpoints nem schema aprovado. |
| Este documento | Métodos, caminhos, nomes de campos, formas de resposta e códigos de erro abaixo são **propostas**, sujeitos à aprovação do Front-end, da equipe de banco e do grupo. |

## Convenções propostas para leitura dos exemplos

- Prefixo `/api/v1/`; identificadores como `u1`, `s1`, `k1`, `l1` e `b1` são referências **opacas ilustrativas**, sem escolha de PK, tabela ou tipo definitivo. Campos JSON exibidos servem para discutir o contrato; **não estabelecem campos obrigatórios finais**.
- Horários usam strings ISO 8601 com offset, por exemplo `2026-10-30T10:00:00-03:00`. O nome dos campos, a zona de apresentação, quem fornece o horário e a precisão serão acordados. As regras puras rejeitam datetimes sem timezone.
- `Público` significa sem sessão/token. `Autenticado` é a proposta para leitura e operações de domínio; a configuração DRF atual exige autenticação por padrão, mas não define as permissões finais. `Gestão a definir` e `escopo próprio/a definir` indicam **autorização pendente**, sem inventar papéis. Para UC001, sessão (com cookie/CSRF) versus token ainda não foi decidido.
- Nos quadros, `—` em entrada significa sem corpo JSON. `401` (não autenticado) e `403` (sem permissão) são respostas propostas para todas as rotas autenticadas, além dos erros específicos indicados. Listas e envelopes JSON são apenas exemplos; paginação ainda não foi definida.

## UC001 — autenticação

| Método e caminho propostos | Parâmetros e JSON de entrada ilustrativo | Resposta de sucesso ilustrativa | Acesso | Erros principais |
|---|---|---|---|---|
| `POST /api/v1/auth/login/` | Sem parâmetro de caminho; `{"identifier":"ana","password":"exemplo"}`. Identificador de login a definir. | `200 {"user":{"id":"u1"}}`; cookie de sessão ou token depende da decisão de autenticação. | Público | `400` entrada inválida; `401` credenciais inválidas. |
| `POST /api/v1/auth/logout/` | Sem parâmetro; corpo `{}`. | `200 {"status":"signed_out"}`. Revogação/expiração depende do mecanismo escolhido. | Autenticado | `401`. |
| `GET /api/v1/auth/me/` | Sem parâmetro; sem corpo. | `200 {"id":"u1"}`. Campos de perfil a definir. | Autenticado | `401`. |

## UC002 — usuários

| Método e caminho propostos | Parâmetros e JSON de entrada ilustrativo | Resposta de sucesso ilustrativa | Acesso | Erros principais |
|---|---|---|---|---|
| `GET /api/v1/users/` | Sem corpo; filtros ainda não definidos. | `200 [{"id":"u1","name":"Ana"}]`. | Autenticado; permissão e alcance da lista a definir | `403`. |
| `POST /api/v1/users/` | `{"name":"Ana"}`; campos de identidade/credencial a definir. | `201 {"id":"u1","name":"Ana"}`. | Autenticado; gestão a definir | `400`, `403`, `409` se houver unicidade acordada. |
| `GET /api/v1/users/{user_id}/` | `user_id` no caminho; sem corpo. | `200 {"id":"u1","name":"Ana"}`. | Autenticado; escopo próprio/gestão a definir | `403`, `404`. |
| `PATCH /api/v1/users/{user_id}/` | `user_id`; `{"name":"Ana Maria"}`. | `200 {"id":"u1","name":"Ana Maria"}`. | Autenticado; escopo próprio/gestão a definir | `400`, `403`, `404`, `409` se aplicável. |

Exclusão, desativação, perfis, recuperação de senha, campos de login e uso de `auth_user` ou tabela própria estão pendentes. Não se propõe `DELETE` antes de decidir como preservar referências históricas. Os campos pessoais exemplificados só deverão ser retornados a quem tiver permissão e dentro do escopo aprovado.

## UC003 — salas e laboratórios

| Método e caminho propostos | Parâmetros e JSON de entrada ilustrativo | Resposta de sucesso ilustrativa | Acesso | Erros principais |
|---|---|---|---|---|
| `GET /api/v1/spaces/` | Sem corpo; filtros por tipo/capacidade a decidir. | `200 [{"id":"s1","code":"LAB-01","kind":"laboratory"}]`. | Autenticado | `403`. |
| `POST /api/v1/spaces/` | `{"code":"LAB-01","kind":"laboratory"}`; nomes/valores a validar. | `201 {"id":"s1","code":"LAB-01","kind":"laboratory"}`. | Autenticado; gestão a definir | `400`, `403`, `409` para identificação duplicada. |
| `GET /api/v1/spaces/{space_id}/` | `space_id`; sem corpo. | `200 {"id":"s1","code":"LAB-01","kind":"laboratory"}`. | Autenticado | `403`, `404`. |
| `PATCH /api/v1/spaces/{space_id}/` | `space_id`; `{"code":"LAB-02"}`. | `200 {"id":"s1","code":"LAB-02","kind":"laboratory"}`. | Autenticado; gestão a definir | `400`, `403`, `404`, `409` para identificação duplicada. |

`code` e `kind` ilustram a identificação única e a distinção sala/laboratório; não são colunas aprovadas. Exclusão/desativação de espaços com chaves ou reservas exige decisão de integridade referencial.

## UC004–UC009 — chaves, empréstimos, disponibilidade e histórico

| Método e caminho propostos | Parâmetros e JSON de entrada ilustrativo | Resposta de sucesso ilustrativa | Acesso | Erros principais |
|---|---|---|---|---|
| `GET /api/v1/keys/` | Sem corpo; filtros por espaço a decidir. | `200 [{"id":"k1","space_id":"s1"}]`. | Autenticado | `403`. |
| `POST /api/v1/keys/` | `{"space_id":"s1"}`; identificação da chave a definir. | `201 {"id":"k1","space_id":"s1"}`. | Autenticado; gestão a definir | `400`, `403`, `404` espaço inexistente, `409` se houver unicidade acordada. |
| `GET /api/v1/keys/{key_id}/` | `key_id`; sem corpo. | `200 {"id":"k1","space_id":"s1"}`. | Autenticado | `403`, `404`. |
| `PATCH /api/v1/keys/{key_id}/` | `key_id`; `{"space_id":"s2"}`. | `200 {"id":"k1","space_id":"s2"}`. | Autenticado; gestão a definir | `400`, `403`, `404`, `409` se empréstimo/histórico impedir mudança. |
| `POST /api/v1/key-loans/` (UC005) | `{"key_id":"k1","responsible_user_id":"u1"}`; origem de `checked_out_at` a decidir. | `201 {"id":"l1","key_id":"k1","responsible_user_id":"u1","checked_out_at":"2026-10-30T10:00:00-03:00","status":"active"}`. | Autenticado; permissão de entrega a definir | `400`, `403`, `404`, `409 KEY_UNAVAILABLE` se empréstimo ativo ou outra restrição aprovada. |
| `POST /api/v1/key-loans/{loan_id}/return/` (UC006) | `loan_id`; corpo `{}`; origem do horário de devolução a decidir. | `200 {"id":"l1","returned_at":"2026-10-30T11:00:00-03:00","status":"returned"}`. | Autenticado; permissão de devolução a definir | `400`, `403`, `404` empréstimo inexistente, `409 LOAN_ALREADY_RETURNED`. |
| `GET /api/v1/keys/{key_id}/loan-availability/` (UC007) | `key_id`; sem corpo. | `200 {"key_id":"k1","has_active_loan":true}`; sem empréstimo, `false`. A referência do empréstimo não é exposta neste exemplo. | Autenticado; permissão de consulta a definir | `403`, `404`. |
| `GET /api/v1/keys/{key_id}/movements/` (UC008) | `key_id`; sem corpo; filtros/paginação pendentes. | `200 {"key_id":"k1","events":[{"type":"checkout","loan_id":"l1","occurred_at":"2026-10-30T10:00:00-03:00"},{"type":"return","loan_id":"l1","occurred_at":"2026-10-30T11:00:00-03:00"}]}`. | Autenticado; escopo do histórico a definir | `403`, `404`. |
| `GET /api/v1/keys/{key_id}/history-report/` (UC009, P3) | `key_id`; formato e período a decidir. | **Exemplo JSON provisório:** `200 {"key_id":"k1","events":[{"loan_id":"l1","type":"checkout"}]}`. Arquivo/exportação ainda não definidos. | Autenticado; permissão de emissão a definir | `400`, `403`, `404`. |

`loan-availability` expõe **somente ausência/presença de empréstimo ativo**, como na PR #4. A regra pura também pode recuperar a referência do empréstimo ativo, mas sua exposição HTTP depende de autorização específica. Não afirma que a chave existe fisicamente, está liberada administrativamente ou pode ser entregue. A entrega precisa revalidar disponibilidade na mesma transação de gravação; um `GET` anterior não reserva a chave. A devolução preserva a retirada e registra evento vinculado ao empréstimo, conforme a PR #3. O exemplo de histórico omite dados pessoais do responsável; a necessidade de exibi-los e a permissão correspondente ainda precisam de aprovação. Nomes `id`, `status` e `events` são candidatos, não schema definido.

## Reservas e disponibilidade de espaços — proposta adicional de MVP

Estas rotas são **propostas da tela/agenda do MVP**, não casos UC001–UC009 aprovados. Não se misturam com disponibilidade de chaves.

| Método e caminho propostos | Parâmetros e JSON de entrada ilustrativo | Resposta de sucesso ilustrativa | Acesso | Erros principais |
|---|---|---|---|---|
| `GET /api/v1/spaces/{space_id}/booking-availability/` | `space_id`; query `start_at=2026-10-30T10:00:00-03:00&end_at=2026-10-30T11:00:00-03:00`; sem corpo. | `200 {"space_id":"s1","start_at":"2026-10-30T10:00:00-03:00","end_at":"2026-10-30T11:00:00-03:00","available":false}`. | Autenticado | `400` intervalo inválido/sem timezone; `403`, `404`. |
| `GET /api/v1/bookings/` | Sem corpo; filtros `space_id`, período e `mine` a decidir. | `200 [{"id":"b1","space_id":"s1","start_at":"2026-10-30T10:00:00-03:00","end_at":"2026-10-30T11:00:00-03:00"}]`. | Autenticado; alcance da lista a definir | `400`, `403`. |
| `POST /api/v1/bookings/` | `{"space_id":"s1","start_at":"2026-10-30T10:00:00-03:00","end_at":"2026-10-30T11:00:00-03:00"}`. | `201 {"id":"b1","space_id":"s1","start_at":"2026-10-30T10:00:00-03:00","end_at":"2026-10-30T11:00:00-03:00"}`. | Autenticado; permissão de reserva a definir | `400` intervalo inválido/sem timezone; `403`, `404`, `409 BOOKING_CONFLICT`. |
| `GET /api/v1/bookings/{booking_id}/` | `booking_id`; sem corpo. | `200 {"id":"b1","space_id":"s1","start_at":"2026-10-30T10:00:00-03:00","end_at":"2026-10-30T11:00:00-03:00"}`. | Autenticado; escopo próprio/gestão a definir | `403`, `404`. |
| `POST /api/v1/bookings/{booking_id}/cancel/` | `booking_id`; corpo `{}`. | `200 {"id":"b1","status":"cancelled"}`. | Autenticado; titular/gestão a definir | `403`, `404`, `409` cancelamento incompatível, se aprovado. |

A PR #2 usa intervalos `[início, fim)`: `10:00–11:00` e `11:00–12:00` não conflitam. A verificação considera somente reservas ativas do **mesmo espaço**. O contrato de estados, cancelamento e conflitos ainda depende de aprovação. A criação de reserva precisa validar e gravar sob proteção transacional/constraint no banco; o `GET` de disponibilidade é apenas consulta instantânea. Não se propõem duração máxima, expediente ou recorrência.

## Formato de erro e status propostos

| HTTP | Uso proposto | Exemplo JSON |
|---|---|---|
| `400 Bad Request` | Corpo, parâmetro ou intervalo inválido; data sem timezone; início não anterior ao fim. | `{"error":{"code":"INVALID_INTERVAL","message":"Início deve ser anterior ao fim."}}` |
| `401 Unauthorized` | Falta autenticação ou credenciais de login inválidas. | `{"error":{"code":"UNAUTHENTICATED","message":"Autenticação necessária."}}` |
| `403 Forbidden` | Identidade conhecida sem permissão para a operação. | `{"error":{"code":"FORBIDDEN","message":"Acesso não permitido."}}` |
| `404 Not Found` | Recurso identificado no caminho não encontrado ou não visível, conforme política a decidir. | `{"error":{"code":"NOT_FOUND","message":"Recurso não encontrado."}}` |
| `409 Conflict` | Estado atual impede operação (chave já emprestada, devolução duplicada, horário de reserva conflitante, identificação única duplicada). | Exemplos abaixo. |

**Chave indisponível por empréstimo ativo:** `409 {"error":{"code":"KEY_UNAVAILABLE","message":"Chave com empréstimo ativo.","details":{"key_id":"k1"}}}`. Se houver outras restrições de disponibilidade, seus códigos e precedência dependem de contrato.

**Horários sobrepostos:** `409 {"error":{"code":"BOOKING_CONFLICT","message":"Horário indisponível para o espaço.","details":{"space_id":"s1"}}}`. Exposição de reservas conflitantes e dados de terceiros depende de permissão/privacidade. Intervalos adjacentes não geram esse erro.

**Devolução repetida:** `409 {"error":{"code":"LOAN_ALREADY_RETURNED","message":"Empréstimo já encerrado."}}`. Os nomes de códigos, mensagens, envelope e a distinção final entre `400`, `404` e `409` precisam ser fechados com o Front-end. Erros internos não devem revelar segredos ou dados de terceiros.

As respostas de sucesso acima usam `200` quando incluem JSON e `201` quando propõem a criação de recurso. **`204 No Content` não foi proposto** porque os exemplos de logout, devolução e cancelamento retornam JSON; pode ser considerado se a equipe optar por respostas vazias. **`422 Unprocessable Content` não foi proposto**: erros de entrada usam `400` e conflitos com o estado atual usam `409` nesta proposta, evitando duas convenções de validação antes do acordo. A forma final de distinguir `401` e `403` também deve acompanhar o mecanismo de autenticação escolhido.

## Alinhamento antes de implementar

### Front-end e produto

- Confirmar quais telas e fluxos de reservas/cancelamento entram no MVP escrito; dashboard pode compor consultas existentes ou exigir contrato próprio.
- Definir login por sessão ou token, transporte de credencial, CSRF/CORS, logout e formato de perfil. Confirmar nomes de campos de entrada/saída, forma de listas e mensagens de erro.
- Definir quais consultas são visíveis por usuário, quem pode gerir usuários/espaços/chaves, entregar/devolver e consultar histórico; não há perfis ou permissões definitivos neste documento.
- Confirmar diferença visual entre **chave sem empréstimo ativo** e **chave efetivamente disponível**, e entre essa informação e a **disponibilidade de horário de um espaço**.
- Definir apresentação de timezone, validação de formulários, retorno de conflitos `409` e tratamento de reservas consecutivas. Decidir necessidade de filtros, paginação, cancelamento e relatório UC009.

### Responsável pelo PostgreSQL

- Acordar tabelas/colunas, identificadores e relações de usuário, espaço, chave, empréstimo, movimentação e eventual reserva; decidir `auth_user` versus identidade própria antes de migrations de autenticação.
- Definir estados ativos/cancelados/encerrados, unicidade de sala, vínculo chave-espaço, retenção do histórico e política de exclusão/desativação.
- Definir quem cria/aplica migrations (inclusive as nativas Django), timezone e precisão dos timestamps, estratégia de testes e banco de teste.
- Projetar constraints/índices e transações para impedir dois empréstimos ativos da mesma chave e reservas sobrepostas do mesmo espaço. A validação pura das PRs #2–#4 não protege gravações concorrentes.

Nenhuma decisão deste documento cria tabela, migration, view, serializer ou endpoint.
