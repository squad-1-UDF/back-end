# Proposta de contratos HTTP do LabTech

**Estado:** proposta para discussão, com UC001 e UC005–UC008 implementadas. Essas rotas usam sessões Django, cookie CSRF e `auth.User` nativo provisoriamente, com testes PostgreSQL isolados. As demais rotas abaixo continuam propostas. `GET /api/v1/health/` confirma apenas que o processo HTTP responde. Consulte [requisitos e contrato inicial](REQUISITOS_E_CONTRATO.md).

## Origem e nível de certeza

| Origem | Conteúdo confirmado ou proposto |
|---|---|
| Requisitos UC001–UC009 | Login; manutenção de usuários, salas/laboratórios e chaves; entrega e devolução de chave; consulta de disponibilidade e histórico de chave; emissão de histórico (UC009, P3). Funções restritas exigem autenticação e permissões. Salas têm identificação única; chaves pertencem a um espaço; entrega exige chave disponível e registra responsável e data/hora; devolução corresponde à entrega; o histórico é preservado. |
| Proposta de MVP do grupo | Login, dashboard, salas, agenda, reservas, minhas reservas e administração. Conflito de horários e cancelamento de reserva **ainda não foram incorporados aos requisitos escritos**. |
| Regras puras integradas à main | [PR #2](https://github.com/squad-1-UDF/back-end/pull/2): intervalos de reserva `[início, fim)`, sem conflito quando consecutivos; filtro por espaço e estado ativo fica com o chamador. [PR #3](https://github.com/squad-1-UDF/back-end/pull/3): retirada/devolução e histórico de eventos. [PR #4](https://github.com/squad-1-UDF/back-end/pull/4): empréstimo ativo e movimentações por chave; ausência de empréstimo ativo não garante disponibilidade física ou administrativa. Essas PRs não são endpoints nem schema aprovado. |
| Este documento | UC001 e UC005–UC008 descrevem comportamento HTTP implementado provisoriamente. Os demais métodos, caminhos, campos, respostas e erros são **propostas**, sujeitos à aprovação do Front-end, da equipe de banco e do grupo. |

## Convenções propostas para leitura dos exemplos

- Prefixo `/api/v1/`; nas rotas ainda propostas, identificadores como `u1`, `s1`, `k1`, `l1` e `b1` são referências **opacas ilustrativas**. UC005–UC008 usam as PKs inteiras de `Key`, `KeyLoan` e `auth.User`.
- Horários usam strings ISO 8601 com offset, por exemplo `2026-10-30T10:00:00-03:00`. Em UC005–UC006, o servidor define os horários; zona de apresentação e precisão das demais propostas ainda serão acordadas. As regras puras rejeitam datetimes sem timezone.
- `Público` significa sem sessão/token. UC005–UC008 exigem sessão; as escritas UC005–UC006 exigem `is_staff` e CSRF. Nas outras propostas, `Autenticado`, `Gestão a definir` e `escopo próprio/a definir` ainda indicam autorização pendente. A identidade e o mecanismo finais continuam em discussão.
- Nos quadros de propostas, `—` em entrada significa sem corpo JSON. **SessionAuthentication responde `403` para acesso anônimo a `me`, `logout` e UC005–UC008** nesta versão, enquanto credenciais incorretas no login respondem `401`. Paginação ainda não foi definida.

## UC001 — autenticação HTTP provisória

| Método e caminho implementados | Entrada provisória | Resposta atual | Acesso | Erros atuais principais |
|---|---|---|---|---|
| `GET /api/v1/auth/csrf/` | Sem corpo. | `204` sem corpo; emite `Set-Cookie: csrftoken=...`, sem abrir sessão nem retornar dados de usuário. | Público, inclusive anônimo. | `405` para outro método com CSRF válido; um POST sem token pode receber `403` do middleware antes da checagem do método. |
| `POST /api/v1/auth/login/` | JSON `{"identifier":"ana","password":"exemplo"}`; ambos os campos são provisórios. | `200 {"user":{"id":7}}` e cookie de sessão, se houver banco de usuários e sessões configurado. | Anônimo permitido; CSRF obrigatório mesmo sem sessão. | `400` JSON inválido; `401` credenciais inválidas ou usuário inativo; `403` CSRF; `405` método; `415` tipo de mídia. |
| `POST /api/v1/auth/logout/` | JSON `{}` ou corpo vazio. | `200 {"status":"signed_out"}`; encerra a sessão Django. | Sessão autenticada e CSRF obrigatório. | `400` corpo não vazio; `403` sem autenticação ou CSRF; `405` método. |
| `GET /api/v1/auth/me/` | Sem corpo. | `200 {"id":7}`; apenas a PK, sem dados pessoais. | Sessão autenticada. | `403` sem autenticação; `405` método. |

`identifier` é encaminhado ao `USERNAME_FIELD` do modelo obtido por `get_user_model()` e ao backend configurado. Não há exigência de email. Por enquanto, usa-se `auth.User` nativo (`username`), sem modelo personalizado. As migrations nativas de `auth`, `contenttypes` e `sessions`, `spaces.0001_initial` e `keys.0001_initial` cobrem a persistência atual. A CI sem banco continua com backend dummy; o job PostgreSQL executa os testes reais de autenticação, espaços, chaves e empréstimos. A identidade definitiva e as demais permissões de domínio continuam pendentes.

**Fluxo do Front-end na mesma origem:** fazer `GET /api/v1/auth/csrf/` com cookies (`credentials: "same-origin"` no `fetch`), ler `csrftoken` de `document.cookie` e enviar esse valor no cabeçalho `X-CSRFToken` do `POST /api/v1/auth/login/`, junto de `Content-Type: application/json` e `credentials: "same-origin"`. Enviar o cookie de sessão nas chamadas a `GET /api/v1/auth/me/` e no `POST /api/v1/auth/logout/`; neste último, enviar também o cabeçalho CSRF e `{}` como corpo JSON. Django renova o token CSRF no login: reler `csrftoken` após a resposta antes de outro POST. `GET /api/v1/auth/csrf/` não autentica o visitante. Os testes HTTP antigos usam mocks; `apps/tests/test_auth_postgres.py` valida o fluxo e a persistência real em PostgreSQL isolado.

**Origens distintas:** esquema, host ou porta diferentes já caracterizam outra origem; `localhost` e `127.0.0.1` também devem ser tratados separadamente. `CORS_ALLOWED_ORIGINS` permite apenas as origens listadas, mas a configuração atual não habilita credenciais CORS (`CORS_ALLOW_CREDENTIALS` é `False`). `CSRF_TRUSTED_ORIGINS` é uma lista separada para validar a origem de POSTs; incluí-la não habilita cookies CORS. Portanto, o fluxo de sessão de um Front-end em outra origem ainda não está configurado. Se essa topologia for aprovada, definir origens exatas, credenciais (`credentials: "include"` no cliente), domínio e política `SameSite` dos cookies, HTTPS e proxy confiável antes de ativá-la. Não usar curingas para liberar origens.

**Ambientes:** `.env.example` usa `DJANGO_DEBUG=true` para desenvolvimento HTTP local; nessa condição, os cookies CSRF e de sessão não recebem `Secure`. Com `DEBUG=false`, ambos usam `Secure` e exigem HTTPS no navegador. Os padrões atuais `SameSite=Lax` e `CSRF_COOKIE_HTTPONLY=False` permitem a leitura do cookie CSRF pelo JavaScript na mesma origem; alterar essas opções exige revisar o fluxo. Em produção atrás de proxy TLS, a identificação segura do esquema pelo Django depende de configuração do proxy confiável. Nenhuma dessas configurações foi ampliada nesta etapa.

Falhas de CSRF retornam `403 {"error":"CSRF inválido ou ausente."}` sem divulgar o motivo interno. Os erros de validação JSON usam respostas do DRF; os formatos definitivos de erro continuam pendentes de acordo com o Front-end.

## UC002 — usuários

| Método e caminho propostos | Parâmetros e JSON de entrada ilustrativo | Resposta de sucesso ilustrativa | Acesso | Erros principais |
|---|---|---|---|---|
| `GET /api/v1/users/` | Sem corpo; filtros ainda não definidos. | `200 [{"id":"u1","name":"Ana"}]`. | Autenticado; permissão e alcance da lista a definir | `403`. |
| `POST /api/v1/users/` | `{"name":"Ana"}`; campos de identidade/credencial a definir. | `201 {"id":"u1","name":"Ana"}`. | Autenticado; gestão a definir | `400`, `403`, `409` se houver unicidade acordada. |
| `GET /api/v1/users/{user_id}/` | `user_id` no caminho; sem corpo. | `200 {"id":"u1","name":"Ana"}`. | Autenticado; escopo próprio/gestão a definir | `403`, `404`. |
| `PATCH /api/v1/users/{user_id}/` | `user_id`; `{"name":"Ana Maria"}`. | `200 {"id":"u1","name":"Ana Maria"}`. | Autenticado; escopo próprio/gestão a definir | `400`, `403`, `404`, `409` se aplicável. |

Exclusão, desativação, perfis, recuperação de senha e campos de login definitivos estão pendentes. `auth_user` é a escolha provisória de UC001; o vínculo com o responsável por uma chave ainda precisa de contrato. Não se propõe `DELETE` antes de decidir como preservar referências históricas. Os campos pessoais exemplificados só deverão ser retornados a quem tiver permissão e dentro do escopo aprovado.

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
| `POST /api/v1/key-loans/` (UC005, implementado) | `{"key_id":1,"responsible_user_id":7}`; inteiros positivos. Horário e operador vêm do servidor. | `201 {"id":5,"key_id":1,"responsible_user_id":7,"checked_out_at":"2026-10-30T10:00:00-03:00","status":"active"}`. | Sessão staff e CSRF | `400`, `403`, `404`, `409 KEY_UNAVAILABLE` se houver empréstimo ativo. |
| `POST /api/v1/key-loans/{loan_id}/return/` (UC006, implementado) | `loan_id` inteiro; corpo JSON `{}`. Horário e operador vêm do servidor. | `200 {"id":5,"returned_at":"2026-10-30T11:00:00-03:00","status":"returned"}`. | Sessão staff e CSRF | `400`, `403`, `404` empréstimo inexistente, `409 LOAN_ALREADY_RETURNED`. |
| `GET /api/v1/keys/{key_id}/loan-availability/` (UC007, implementado) | `key_id` inteiro; sem corpo. | `200 {"key_id":1,"has_active_loan":true}`; sem empréstimo, `false`. | Sessão autenticada | `403`, `404`. |
| `GET /api/v1/keys/{key_id}/movements/` (UC008, implementado) | `key_id` inteiro; sem corpo. Filtros/paginação pendentes. | `200 {"key_id":1,"events":[{"type":"checkout","loan_id":5,"occurred_at":"2026-10-30T10:00:00-03:00"},{"type":"return","loan_id":5,"occurred_at":"2026-10-30T11:00:00-03:00"}]}`. | Sessão autenticada | `403`, `404`. |
| `GET /api/v1/keys/{key_id}/history-report/` (UC009, P3) | `key_id`; formato e período a decidir. | **Exemplo JSON provisório:** `200 {"key_id":"k1","events":[{"loan_id":"l1","type":"checkout"}]}`. Arquivo/exportação ainda não definidos. | Autenticado; permissão de emissão a definir | `400`, `403`, `404`. |

`loan-availability` expõe **somente ausência/presença de empréstimo ativo**. Não afirma que a chave existe fisicamente, está liberada administrativamente ou pode ser entregue. A retirada revalida o histórico na transação; um `GET` anterior não reserva a chave. A devolução preserva a retirada e registra evento vinculado ao empréstimo. O histórico é ordenado por horário e ID, contém apenas tipo, empréstimo e horário e não oferece alteração ou exclusão. Os erros HTTP de UC005–UC008 usam `error.code` e `error.message`; erros `400` também incluem `error.details`. Falhas de CSRF mantêm a resposta de UC001: `403 {"error":"CSRF inválido ou ausente."}`. Identificadores, autorização e formato de resposta das outras rotas continuam sujeitos à integração com o Front-end.

## Reservas e disponibilidade de espaços — implementação provisória do MVP

Estas rotas atendem à proposta de reservas do MVP; não fazem parte dos casos UC001–UC009 aprovados. Usam `auth.User`, autenticação por sessão e IDs inteiros. `POST` exige CSRF. As datas de entrada são ISO 8601 com offset explícito; as respostas seguem o timezone configurado no Django.

| Método e caminho | Entrada | Resposta de sucesso | Acesso |
|---|---|---|---|
| `POST /api/v1/bookings/` | JSON com `space_id` inteiro, `start_at` e `end_at` | `201` com `id`, `space_id`, `start_at`, `end_at`, `status: "active"`, `created_at` e `cancelled_at: null` | Usuário autenticado; responsável é sempre a sessão |
| `GET /api/v1/bookings/` | Filtros opcionais `space_id`, `status=active\|cancelled`, `scope=mine\|all`, `limit` e `offset` | `200` com lista dos mesmos campos, ordenada por início e ID | Por padrão somente próprias; `scope=all` exige staff |
| `GET /api/v1/bookings/{booking_id}/` | ID inteiro | `200` com os campos da reserva | Titular ou staff; terceiros recebem `404` |
| `POST /api/v1/bookings/{booking_id}/cancel/` | JSON `{}` | `200` com `id`, `status: "cancelled"` e `cancelled_at` | Titular ou staff; terceiros recebem `404` |
| `GET /api/v1/spaces/{space_id}/booking-availability/` | Query `start_at` e `end_at` | `200` com `space_id`, intervalo e `available` | Autenticado |
| `GET /api/v1/spaces/{space_id}/booking-agenda/` | Query `start_at` e `end_at` | `200` com `space_id`, intervalo e `occupied: [{"start_at": "...", "end_at": "..."}]` | Autenticado |

Reservas usam intervalos `[início, fim)`: horários consecutivos não conflitam. A constraint PostgreSQL impede sobreposição de reservas **ativas no mesmo espaço**, inclusive gravações concorrentes ou diretas. Cancelar preserva o registro e libera seu intervalo para nova reserva. Disponibilidade e agenda consultam apenas reservas ativas; não expõem usuário e representam uma fotografia do momento, sem garantir uma reserva futura. O banco não impõe duração máxima, expediente ou recorrência.

A listagem retorna no máximo 100 reservas por chamada (`limit` padrão 100, máximo 100; `offset` padrão 0). As consultas de disponibilidade e agenda exigem intervalo de até 31 dias. Se houver mais de 1.000 horários ocupados na janela, a agenda retorna `400 INVALID_REQUEST` para que o cliente consulte uma janela menor; ela nunca devolve uma lista truncada como se estivesse completa. Esses limites são do contrato de consulta e não limitam a duração de uma reserva.

Na implantação, a migration instala `btree_gist` antes de criar a constraint. No PostgreSQL 16, essa extensão é confiável e o papel que aplica a migration precisa de privilégio `CREATE` no banco para instalá-la; a criação da tabela também requer privilégio de criação no schema de destino. Se a política do ambiente não permitir esse privilégio, um administrador deve instalar `btree_gist` previamente **no mesmo banco** antes da migration. Consulte a [documentação PostgreSQL](https://www.postgresql.org/docs/16/btree-gist.html) e a [operação do Django](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/operations/).

Erros de entrada usam `400 INVALID_REQUEST`, falta de sessão ou permissão usa `403 FORBIDDEN`, espaço/reserva ausente ou reserva alheia usa `404 NOT_FOUND`, sobreposição usa `409 BOOKING_CONFLICT` e cancelamento repetido usa `409 BOOKING_ALREADY_CANCELLED`. O envelope comum é `{"error":{"code":"...","message":"..."}}`; erros `400` incluem `details`. Falha de CSRF segue o corpo já adotado por UC001. Somente conflitos reconhecidos são convertidos em `409`.

## Formato de erro e status propostos

| HTTP | Uso proposto | Exemplo JSON |
|---|---|---|
| `400 Bad Request` | Corpo ou parâmetro inválido. UC005–UC006 e reservas usam `INVALID_REQUEST` e `details`. | `{"error":{"code":"INVALID_REQUEST","message":"Entrada inválida.","details":{"key_id":["Informe um inteiro."]}}}` |
| `401 Unauthorized` | Credenciais de login inválidas em UC001; UC005–UC008 usam `403` sem sessão. | `{"error":{"code":"UNAUTHENTICATED","message":"Autenticação necessária."}}` (proposta para outras rotas) |
| `403 Forbidden` | Falta de sessão ou de permissão staff em UC005–UC008; falhas de CSRF têm o corpo já usado por UC001. | `{"error":{"code":"FORBIDDEN","message":"Acesso não permitido."}}` |
| `404 Not Found` | Recurso identificado no caminho não encontrado ou não visível, conforme política a decidir. | `{"error":{"code":"NOT_FOUND","message":"Recurso não encontrado."}}` |
| `409 Conflict` | Estado atual impede operação (chave já emprestada, devolução duplicada, horário de reserva conflitante, identificação única duplicada). | Exemplos abaixo. |

**Chave indisponível por empréstimo ativo:** `409 {"error":{"code":"KEY_UNAVAILABLE","message":"Chave com empréstimo ativo.","details":{"key_id":1}}}`. Outras restrições de disponibilidade não são verificadas por UC005–UC008.

**Horários sobrepostos:** `409 {"error":{"code":"BOOKING_CONFLICT","message":"Horário indisponível para o espaço.","details":{"space_id":1}}}`. A resposta não expõe reservas conflitantes nem dados pessoais. Intervalos adjacentes não geram esse erro.

**Devolução repetida:** `409 {"error":{"code":"LOAN_ALREADY_RETURNED","message":"Empréstimo já encerrado."}}`. Os nomes de códigos, mensagens, envelope e a distinção final entre `400`, `404` e `409` precisam ser fechados com o Front-end. Erros internos não devem revelar segredos ou dados de terceiros.

As respostas de sucesso acima usam `200` quando incluem JSON e `201` quando propõem a criação de recurso. **`204 No Content` não foi proposto** porque os exemplos de logout, devolução e cancelamento retornam JSON; pode ser considerado se a equipe optar por respostas vazias. **`422 Unprocessable Content` não foi proposto**: erros de entrada usam `400` e conflitos com o estado atual usam `409` nesta proposta, evitando duas convenções de validação antes do acordo. A forma final de distinguir `401` e `403` também deve acompanhar o mecanismo de autenticação escolhido.

## Pendências de alinhamento

### Front-end e produto

- Confirmar se os fluxos de reservas/cancelamento já implementados entram no MVP escrito; dashboard pode compor consultas existentes ou exigir contrato próprio.
- Definir login por sessão ou token, transporte de credencial, CSRF/CORS, logout e formato de perfil. Confirmar nomes de campos de entrada/saída, forma de listas e mensagens de erro.
- Definir quais consultas são visíveis por usuário, quem pode gerir usuários/espaços/chaves, entregar/devolver e consultar histórico; não há perfis ou permissões definitivos neste documento.
- Confirmar diferença visual entre **chave sem empréstimo ativo** e **chave efetivamente disponível**, e entre essa informação e a **disponibilidade de horário de um espaço**.
- Revisar com o Front-end a apresentação de timezone, validação de formulários e retorno de conflitos `409`. Decidir necessidade de paginação e do relatório UC009.

### Responsável pelo PostgreSQL

- Revisar as tabelas e relações de usuário, espaço, chave, empréstimo, movimentação e reserva; `auth_user` segue como escolha provisória.
- Definir estados ativos/cancelados/encerrados, unicidade de sala, vínculo chave-espaço, retenção do histórico e política de exclusão/desativação.
- Definir quem cria/aplica migrations (inclusive as nativas Django), timezone e precisão dos timestamps, estratégia de testes e banco de teste.
- Revisar a operação das constraints e transações já implementadas para empréstimos ativos e reservas sobrepostas, especialmente antes da implantação compartilhada.

UC005–UC008 usam a persistência de chaves já integrada à `main` e não implementam o CRUD da UC004. Reservas e agenda agora têm implementação provisória nesta branch; sua autorização e seu contrato ainda precisam de revisão conjunta. O relatório UC009 e as demais rotas propostas seguem pendentes.
