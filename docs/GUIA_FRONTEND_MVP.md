# Guia curto para o Front-end — API MVP integrada

Base: `/api/v1/`. Os exemplos usam IDs inteiros e horários ISO 8601 com offset. As rotas descritas abaixo estão na `main`. A UC004 ainda não tem endpoint integrado para cadastrar ou editar chaves. `GET /health/` apenas confirma que o processo HTTP responde.

## Sessão e CSRF

1. `GET /auth/csrf/` retorna `204`, define o cookie `csrftoken` e não autentica o usuário.
2. `POST /auth/login/` com `Content-Type: application/json`, cookies e `X-CSRFToken: <csrftoken>`; corpo `{"identifier":"ana","password":"senha"}`. Retorna `200 {"user":{"id":7}}` e cookie `sessionid`. Credenciais inválidas retornam `401 {"error":"Credenciais inválidas."}`.
3. Releia `csrftoken` **após o login**, pois o Django o renova. Na mesma origem, use `credentials: "same-origin"` em cada `fetch`: o navegador envia `sessionid` nas chamadas autenticadas. Envie também `X-CSRFToken` em todo POST/PATCH, inclusive login e logout. O cookie `csrftoken` pode ser lido por JavaScript nessa configuração (`CSRF_COOKIE_HTTPONLY=False`).
4. `GET /auth/me/` retorna `200 {"id":7}`. `POST /auth/logout/` com corpo `{}` e CSRF retorna `200 {"status":"signed_out"}` e encerra a sessão.

**Origens distintas:** mudar esquema, host ou porta já muda a origem; `localhost` e `127.0.0.1` também são distintos. A configuração atual não habilita cookies em CORS (`CORS_ALLOW_CREDENTIALS=False`), portanto o fluxo de sessão de um Front-end em outra origem ainda não funciona. `CORS_ALLOWED_ORIGINS` autoriza apenas origens listadas e `CSRF_TRUSTED_ORIGINS` valida a origem de escritas; configurar uma lista não substitui a outra nem habilita credenciais. Antes de usar `credentials: "include"`, a equipe precisa aprovar origens exatas, credenciais CORS, domínio e política `SameSite` dos cookies (hoje `Lax`), HTTPS e proxy confiável. Não usar curingas. Com `DJANGO_DEBUG=false`, os cookies de sessão e CSRF têm `Secure` e exigem HTTPS; em desenvolvimento local com `DEBUG=true`, não têm `Secure`. Falha de CSRF retorna `403 {"error":"CSRF inválido ou ausente."}`.

## Endpoints de domínio

| Método e URL | JSON de entrada | JSON de sucesso (exemplo) | Permissão |
|---|---|---|---|
| `GET /spaces/` | Sem corpo | `200 [{"id":1,"code":"LAB-01","kind":"laboratory"}]` (ou `[]`) | Autenticado |
| `POST /spaces/` | `{"code":"LAB-01","kind":"laboratory"}` | `201 {"id":1,"code":"LAB-01","kind":"laboratory"}` | Staff + CSRF |
| `GET /spaces/{space_id}/` | Sem corpo | `200 {"id":1,"code":"LAB-01","kind":"laboratory"}` | Autenticado |
| `PATCH /spaces/{space_id}/` | JSON parcial, por exemplo `{"code":"LAB-02"}` | `200 {"id":1,"code":"LAB-02","kind":"laboratory"}` | Staff + CSRF |
| `POST /bookings/` | `{"space_id":1,"start_at":"2026-11-20T10:00:00-03:00","end_at":"2026-11-20T11:00:00-03:00"}` | `201 {"id":5,"space_id":1,"start_at":"...","end_at":"...","status":"active","created_at":"...","cancelled_at":null}` | Autenticado + CSRF; titular é a sessão |
| `GET /bookings/` | Sem corpo; filtros opcionais `space_id`, `status`, `scope`, `limit`, `offset` | `200` com lista de reservas no formato acima | Por padrão, só próprias; `scope=all` exige staff |
| `GET /bookings/{booking_id}/` | Sem corpo | `200` com reserva no formato acima | Titular ou staff |
| `POST /bookings/{booking_id}/cancel/` | `{}` | `200 {"id":5,"status":"cancelled","cancelled_at":"..."}` | Titular ou staff + CSRF |
| `GET /spaces/{space_id}/booking-availability/?start_at=...&end_at=...` | Query com intervalo ISO 8601 e offset | `200 {"space_id":1,"start_at":"...","end_at":"...","available":false}` | Autenticado |
| `GET /spaces/{space_id}/booking-agenda/?start_at=...&end_at=...` | Mesma query | `200 {"space_id":1,"start_at":"...","end_at":"...","occupied":[{"start_at":"...","end_at":"..."}]}` | Autenticado |
| `POST /key-loans/` | `{"key_id":2,"responsible_user_id":7}` | `201 {"id":9,"key_id":2,"responsible_user_id":7,"checked_out_at":"...","status":"active"}` | Staff + CSRF |
| `POST /key-loans/{loan_id}/return/` | `{}` | `200 {"id":9,"returned_at":"...","status":"returned"}` | Staff + CSRF |
| `GET /keys/{key_id}/loan-availability/` | Sem corpo | `200 {"key_id":2,"has_active_loan":true}` | Autenticado |
| `GET /keys/{key_id}/movements/` | Sem corpo | `200 {"key_id":2,"events":[{"type":"checkout","loan_id":9,"occurred_at":"..."},{"type":"return","loan_id":9,"occurred_at":"..."}]}` | Autenticado |

`GET /health/` retorna `200 {"status":"ok","service":"labtech-api"}` sem sessão. Horários de saída são serializados no timezone configurado no Django. Reserva usa intervalo `[início, fim)`; após cancelamento, o mesmo horário volta a ficar disponível. `has_active_loan=false` informa apenas que não há empréstimo ativo, sem garantir disponibilidade física ou administrativa da chave.

## Erros relevantes

As APIs de espaços, reservas e empréstimos usam `{"error":{"code":"...","message":"..."}}`. Erros `400` também incluem `error.details`.

| HTTP | Quando ocorre | Código de exemplo |
|---|---|---|
| `400` | JSON, identificador ou intervalo inválido | `INVALID_REQUEST` |
| `403` | Sem sessão, sem permissão staff, ou `scope=all` por usuário comum | `FORBIDDEN` |
| `404` | Espaço, reserva, chave ou empréstimo ausente; reserva de outro usuário também é ocultada | `NOT_FOUND` |
| `409` | Código de espaço duplicado | `DUPLICATE_CODE` |
| `409` | Reserva ativa sobreposta no mesmo espaço | `BOOKING_CONFLICT` |
| `409` | Chave com empréstimo ativo | `KEY_UNAVAILABLE` |
| `409` | Reserva já cancelada ou empréstimo já devolvido | `BOOKING_ALREADY_CANCELLED` ou `LOAN_ALREADY_RETURNED` |

Exemplo de conflito: `409 {"error":{"code":"BOOKING_CONFLICT","message":"Horário indisponível para o espaço.","details":{"space_id":1}}}`. A falha de CSRF e as credenciais inválidas do login usam os corpos específicos descritos acima.
