# Sistema de Gestão de Laboratórios e Salas — API

API em Python 3.13, Django 5.2 e Django REST Framework. UC001 oferece `GET /api/v1/auth/csrf/`, `POST /api/v1/auth/login/`, `POST /api/v1/auth/logout/` e `GET /api/v1/auth/me/` com `auth.User` nativo e sessões Django. UC003 já tem o model `Space` e sua migration; a API de espaços permanece pendente de integração.

## Preparar o ambiente local

1. Instale Python 3.13 e crie um ambiente virtual:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[dev]"
   ```

   Em Linux/macOS, use `python3.13 -m venv .venv` e `source .venv/bin/activate`.

2. Crie o `.env` local ignorado pelo Git e gere segredos locais:

   ```powershell
   Copy-Item .env.example .env
   $secret = python -c "import secrets; print(secrets.token_urlsafe(50))"
   $dbPassword = python -c "import secrets; print(secrets.token_urlsafe(32))"
   (Get-Content .env) -replace '^DJANGO_SECRET_KEY=.*$', "DJANGO_SECRET_KEY=$secret" -replace '^DB_PASSWORD=.*$', "DB_PASSWORD=$dbPassword" | Set-Content .env
   ```

3. Inicie o PostgreSQL 16 isolado do Compose e aplique as migrations **somente nesse banco local**. A versão 16 é [suportada pelo Django 5.2](https://docs.djangoproject.com/en/5.2/releases/5.2/#dropped-support-for-postgresql-13) e [continua sob suporte do PostgreSQL](https://www.postgresql.org/support/versioning/):

   ```powershell
   docker compose up --wait -d db
   docker compose ps db
   docker compose build api
   docker compose run --rm --no-deps api python manage.py migrate
   ```

   O serviço publica apenas `127.0.0.1:55432` e usa um volume próprio. O comando de migration roda no contêiner da API com `DB_HOST=db`, ligado ao PostgreSQL deste Compose; não usa banco compartilhado, produção ou Neon. `migrate` aplica as migrations nativas de `contenttypes`, `auth` e `sessions`, além de `spaces.0001_initial` e `keys.0001_initial`. Para criar uma conta local, use `python manage.py createsuperuser`.

4. Verifique e inicie a API:

   ```powershell
   python manage.py check
   python manage.py runserver
   ```

   Acesse `http://127.0.0.1:8000/api/v1/health/`. O login e a sessão usam o PostgreSQL local. O model de espaços ainda não possui endpoints integrados nesta branch.

## Verificações

Com o ambiente ativado e `.env` configurado:

```powershell
python -m pip check
python -m ruff check .
python -m ruff format --check .
python manage.py check
python -m pytest -q
python -m pytest -q apps/tests/test_auth_postgres.py
python -m pytest -q apps/tests/test_spaces_postgres.py
python -m pytest -q apps/tests/test_keys_postgres.py
```

O pytest-django cria e remove `test_labtech_local`, separado de `labtech_local`, e aplica ali as migrations nativas e `spaces.0001_initial` para os testes integrados. Para executar somente os testes sem banco, faça `$env:DB_DISABLED = "true"; python -m pytest -q; Remove-Item Env:DB_DISABLED`; os testes PostgreSQL ficam ignorados nesse modo, mesmo com `.env` local. O servidor `runserver` não é um servidor de produção.

## Docker para desenvolvimento

Com Docker ativo e `.env` criado, `docker compose up --build -d` inicia PostgreSQL e API para desenvolvimento. A API fica em `http://127.0.0.1:8000/` por padrão; se a porta estiver ocupada, ajuste `API_PORT` no `.env`. O contêiner usa `DB_HOST=db` e `DB_PORT=5432` e não aplica migrations automaticamente. Para migrar pelo contêiner, use `docker compose exec api python manage.py migrate` somente após verificar que o serviço `db` é o PostgreSQL local do Compose.

## Integração contínua

O job `checks` usa `DB_DISABLED=true` e backend `dummy`, preservando os testes sem banco. O job `postgres-uc001` mantém esse identificador para preservar o check existente e executa os testes reais de UC001, do model UC003 e da persistência de chaves. Ele sobe PostgreSQL 16 efêmero; somente esse serviço descartável usa autenticação `trust`, sem senha nos logs. O pytest-django cria seu banco de teste e aplica migrations nativas, de `spaces` e de `keys`. Nenhum job depende de banco externo.

## Configuração por ambiente

| Ambiente | Credenciais | Banco |
|---|---|---|
| Desenvolvimento local | `.env` ignorado, gerado acima | Compose em `127.0.0.1:55432` |
| Testes sem banco | `DB_DISABLED=true` no processo (ou `DB_NAME` vazio sem `.env` local) | Backend `dummy`, sem migrations |
| Testes integrados | `.env` local ou variáveis do job CI | `test_<DB_NAME>` criado pelo pytest-django |
| Produção | Variáveis injetadas pelo ambiente de implantação, nunca `.env.example` | PostgreSQL externo via `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` |

Em produção, `DJANGO_DEBUG=false` e as políticas de HTTPS, cookies, origem e proxy devem ser configuradas antes da implantação. As migrations de produção são responsabilidade do processo de implantação, fora deste roteiro.

## Próxima etapa

UC001 usa provisoriamente `auth.User` nativo. O esquema de espaços está em [docs/MODELO_SPACES.md](docs/MODELO_SPACES.md); a integração HTTP permanece com a PR #7. A persistência de chaves, empréstimos e movimentações está em [docs/MODELO_CHAVES.md](docs/MODELO_CHAVES.md), sem endpoints HTTP nesta branch. Responsáveis externos, permissões, reservas e demais contratos de domínio ainda exigem decisão. O fluxo de cookies e `X-CSRFToken` está em [docs/API_CONTRATOS_MVP.md](docs/API_CONTRATOS_MVP.md).

Licença: [GNU GPL v3](LICENSE).
