# Guia curto para o Front-end — API MVP integrada

Base: `/api/v1/`. Os exemplos usam IDs inteiros e horários ISO 8601 com offset. As rotas descritas abaixo estão na `main`. A UC004 (cadastro de chaves) está descrita em [Chaves e empréstimos](#chaves-e-empréstimos). `GET /health/` apenas confirma que o processo HTTP responde.

## Sessão e CSRF

1. `GET /auth/csrf/` retorna `204`, define o cookie `csrftoken` e não autentica o usuário.
2. `POST /auth/login/` com `Content-Type: application/json`, cookies e `X-CSRFToken: <csrftoken>`; corpo `{"identifier":"ana","password":"senha"}`. Retorna `200 {"user":{"id":7}}` e cookie `sessionid`. Credenciais inválidas retornam `401 {"error":"Credenciais inválidas."}`.
3. Releia `csrftoken` **após o login**, pois o Django o renova. Na mesma origem, use `credentials: "same-origin"` em cada `fetch`: o navegador envia `sessionid` nas chamadas autenticadas. Envie também `X-CSRFToken` em todo POST/PATCH, inclusive login e logout. O cookie `csrftoken` pode ser lido por JavaScript nessa configuração (`CSRF_COOKIE_HTTPONLY=False`).
4. `GET /auth/me/` retorna `200 {"id":7,"username":"ana","name":"Ana Costa","email":"ana@udf.edu.br","role":"admin","is_staff":true}`. `name` é o nome completo ou, se vazio, o `username`. `role` é `admin`, `employee` ou `student` (veja "Usuários e perfis"); `is_staff` continua presente. Use os dados da sessão para exibir ações administrativas; a seleção de perfil na tela não concede permissão. Sem sessão, retorna `403`. `POST /auth/logout/` com corpo `{}` e CSRF retorna `200 {"status":"signed_out"}` e encerra a sessão.

**Origens distintas:** mudar esquema, host ou porta já muda a origem; `localhost` e `127.0.0.1` também são distintos. A configuração atual não habilita cookies em CORS (`CORS_ALLOW_CREDENTIALS=False`), portanto o fluxo de sessão de um Front-end em outra origem ainda não funciona. `CORS_ALLOWED_ORIGINS` autoriza apenas origens listadas e `CSRF_TRUSTED_ORIGINS` valida a origem de escritas; configurar uma lista não substitui a outra nem habilita credenciais. Antes de usar `credentials: "include"`, a equipe precisa aprovar origens exatas, credenciais CORS, domínio e política `SameSite` dos cookies (hoje `Lax`), HTTPS e proxy confiável. Não usar curingas. Com `DJANGO_DEBUG=false`, os cookies de sessão e CSRF têm `Secure` e exigem HTTPS; em desenvolvimento local com `DEBUG=true`, não têm `Secure`. Falha de CSRF retorna `403 {"error":"CSRF inválido ou ausente."}`.

## Usuários e perfis (UC002)

O papel é derivado do `auth.User`, sem tabela própria:

- `admin`: superusuário ou membro do grupo `admin`;
- `employee`: `is_staff=true` sem ser admin;
- `student`: os demais.

Ao gravar `role` pela API: `admin` coloca no grupo `admin` e define `is_staff=true`; `employee` tira do grupo e define `is_staff=true`; `student` tira do grupo e define `is_staff=false`. Superusuário não é rebaixado pela API.

| Método e URL | JSON de entrada | JSON de sucesso (exemplo) | Permissão |
|---|---|---|---|
| `GET /users/` | Sem corpo; filtros opcionais `role`, `is_active` (`true`/`false`), `q` (busca em username, nome e e-mail), `limit` (1–100, padrão 100), `offset` | `200 [{"id":7,"username":"ana","name":"Ana Costa","email":"ana@udf.edu.br","role":"admin","is_active":true,"date_joined":"..."}]`, ordenado por nome | Staff (`employee` ou `admin`) |
| `POST /users/` | `{"username":"bruno","name":"Bruno Lima","email":"bruno@udf.edu.br","role":"student","password":"..."}`; `name` é opcional | `201` com o usuário no formato acima | Admin + CSRF |
| `GET /users/{user_id}/` | Sem corpo | `200` com o usuário | Staff |
| `PATCH /users/{user_id}/` | JSON parcial com `name`, `email`, `role`, `is_active`, `password` | `200` com o usuário | Admin + CSRF |

Regras: `username` e `email` são únicos sem diferenciar maiúsculas (`409 DUPLICATE_USERNAME` ou `409 DUPLICATE_EMAIL`, com `details.field`); `email` é obrigatório no cadastro; a senha passa pelos validadores do Django (`400` com `details.password`); campos desconhecidos geram `400`. Um admin não pode desativar a si mesmo nem tirar o próprio papel de admin (`400`). O `name` é dividido em `first_name` (primeira palavra) e `last_name` (restante). Não existe `DELETE` (`405`): para retirar acesso, use `{"is_active":false}`; usuário inativo não consegue fazer login.

## Endpoints de domínio

| Método e URL | JSON de entrada | JSON de sucesso (exemplo) | Permissão |
|---|---|---|---|
| `GET /spaces/` | Sem corpo; filtros opcionais `is_active=true\|false` e `kind=room\|laboratory` | `200 [{"id":1,"code":"LAB-01","kind":"laboratory","name":"Laboratório de Redes","capacity":30,"location":"Bloco B","is_active":true}]` (ou `[]`), por `id` | Autenticado |
| `POST /spaces/` | `{"code":"LAB-01","kind":"laboratory"}`; opcionais `name`, `capacity`, `location`, `is_active` | `201 {"id":1,"code":"LAB-01","kind":"laboratory","name":"Laboratório de Redes","capacity":30,"location":"Bloco B","is_active":true}` | Staff + CSRF |
| `GET /spaces/{space_id}/` | Sem corpo | `200` com espaço no formato acima | Autenticado |
| `PATCH /spaces/{space_id}/` | JSON parcial, por exemplo `{"code":"LAB-02"}` ou `{"is_active":false}` | `200` com espaço no formato acima | Staff + CSRF |
| `POST /bookings/` | `{"space_id":1,"start_at":"2026-11-20T10:00:00-03:00","end_at":"2026-11-20T11:00:00-03:00"}` | `201 {"id":5,"space_id":1,"start_at":"...","end_at":"...","status":"active","created_at":"...","cancelled_at":null}` | Staff + CSRF; titular é a sessão |
| `GET /bookings/` | Sem corpo; filtros opcionais `space_id`, `status`, `scope`, `limit`, `offset` | `200` com lista de reservas no formato acima | Staff; por padrão, só próprias; `scope=all` lista todas |
| `GET /bookings/{booking_id}/` | Sem corpo | `200` com reserva no formato acima | Staff |
| `POST /bookings/{booking_id}/cancel/` | `{}` | `200 {"id":5,"status":"cancelled","cancelled_at":"..."}` | Staff + CSRF |
| `GET /spaces/{space_id}/booking-availability/?start_at=...&end_at=...` | Query com intervalo ISO 8601 e offset | `200 {"space_id":1,"start_at":"...","end_at":"...","available":false}` | Autenticado |
| `GET /spaces/{space_id}/booking-agenda/?start_at=...&end_at=...` | Mesma query | `200 {"space_id":1,"start_at":"...","end_at":"...","occupied":[{"start_at":"...","end_at":"..."}]}` | Autenticado |
| `GET /keys/` | Sem corpo; filtros opcionais `space_id`, `status`, `has_active_loan=true\|false` | `200 [KeyOut]` (ou `[]`), por `id` | Staff |
| `POST /keys/` | `{"space_id":1,"label":"LAB-01-A"}`; opcional `"status"` | `201 KeyOut` | Staff + CSRF |
| `GET /keys/{key_id}/` | Sem corpo | `200 KeyOut` | Staff |
| `PATCH /keys/{key_id}/` | JSON parcial com `label`, `status` e/ou `space_id` | `200 KeyOut` | Staff + CSRF |
| `GET /key-loans/` | Sem corpo; filtros opcionais `status=active\|returned`, `key_id`, `space_id`, `responsible_user_id`, `limit` (1–100, padrão 100), `offset` | `200 [LoanOut]`, mais recentes primeiro | Staff |
| `POST /key-loans/` | `{"key_id":2,"responsible_user_id":7}` | `201 {"id":9,"key_id":2,"key_label":"LAB-01-A","space_id":1,"space_code":"LAB-01","responsible_user_id":7,"responsible_name":"Ana Costa","checkout_operator_id":3,"checked_out_at":"...","returned_at":null,"return_operator_id":null,"status":"active"}` | Staff + CSRF |
| `POST /key-loans/{loan_id}/return/` | `{}` | `200 LoanOut` com `returned_at`, `return_operator_id` e `"status":"returned"` | Staff + CSRF |
| `GET /keys/{key_id}/loan-availability/` | Sem corpo | `200 {"key_id":2,"has_active_loan":true}` | Staff |
| `GET /keys/{key_id}/movements/` | Sem corpo | `200 {"key_id":2,"events":[{"type":"checkout","loan_id":9,"occurred_at":"..."},{"type":"return","loan_id":9,"occurred_at":"..."}]}` | Staff |

### Chaves e empréstimos

`KeyOut`:

```json
{"id":2,"space_id":1,"space_code":"LAB-01","label":"LAB-01-A","status":"available","has_active_loan":true,
 "active_loan":{"id":9,"responsible_user_id":7,"responsible_name":"Ana Costa","checked_out_at":"..."}}
```

Sem empréstimo ativo, `has_active_loan` é `false` e `active_loan` é `null`. `LoanOut` é o formato completo mostrado no `POST /key-loans/` acima; `responsible_name` é o nome completo do usuário ou, se vazio, o `username`.

- `label` tem até 40 caracteres, é obrigatório e único sem diferenciar maiúsculas nem espaços nas pontas (`"lab-01-a "` colide com `"LAB-01-A"`). Os espaços das pontas são removidos ao gravar. Rótulo repetido retorna `400 INVALID_REQUEST` com `details.label`. Chaves que já existiam antes desta versão receberam `CHAVE-<id>`.
- `status`: `available` (padrão), `maintenance`, `lost` ou `inactive`. Só chaves `available` e sem empréstimo ativo podem ser retiradas; caso contrário, `409 KEY_UNAVAILABLE`. A devolução de um empréstimo ativo é aceita qualquer que seja o `status`.
- Trocar o `space_id` de uma chave que já teve empréstimo retorna `409 KEY_SPACE_LOCKED`.
- Espaço inexistente em `POST`/`PATCH` de chave retorna `404 NOT_FOUND`. Nada é apagado: para tirar uma chave ou um espaço de uso, altere `status` ou `is_active`.
- Espaço: `name` e `location` têm até 120 caracteres (padrão `""`); `capacity` é inteiro positivo ou `null`; `is_active` é `true` ou `false` (padrão `true`).

`GET /health/` retorna `200 {"status":"ok","service":"labtech-api"}` sem sessão. Horários de saída são serializados no timezone configurado no Django. Reserva usa intervalo `[início, fim)`; após cancelamento, o mesmo horário volta a ficar disponível. `has_active_loan=false` informa apenas que não há empréstimo ativo; para saber se a chave pode ser retirada, confira também `status == "available"`.

## Erros relevantes

As APIs de usuários, espaços, reservas e empréstimos usam `{"error":{"code":"...","message":"..."}}`. Erros `400` também incluem `error.details`.

| HTTP | Quando ocorre | Código de exemplo |
|---|---|---|
| `400` | JSON, identificador, filtro ou intervalo inválido; rótulo de chave repetido | `INVALID_REQUEST` |
| `403` | Sem sessão, sem permissão staff, ou `scope=all` por usuário comum | `FORBIDDEN` |
| `404` | Espaço, reserva, chave ou empréstimo ausente; reserva de outro usuário também é ocultada | `NOT_FOUND` |
| `409` | Código de espaço duplicado | `DUPLICATE_CODE` |
| `409` | Username ou e-mail de usuário já usado | `DUPLICATE_USERNAME` ou `DUPLICATE_EMAIL` |
| `409` | Reserva ativa sobreposta no mesmo espaço | `BOOKING_CONFLICT` |
| `409` | Chave com empréstimo ativo ou com `status` diferente de `available` | `KEY_UNAVAILABLE` |
| `409` | Troca de espaço de chave com histórico de empréstimo | `KEY_SPACE_LOCKED` |
| `409` | Reserva já cancelada ou empréstimo já devolvido | `BOOKING_ALREADY_CANCELLED` ou `LOAN_ALREADY_RETURNED` |

Exemplo de conflito: `409 {"error":{"code":"BOOKING_CONFLICT","message":"Horário indisponível para o espaço.","details":{"space_id":1}}}`. A falha de CSRF e as credenciais inválidas do login usam os corpos específicos descritos acima.
