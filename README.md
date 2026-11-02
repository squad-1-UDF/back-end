# Sistema de Gestão de Laboratórios e Salas — API

Scaffold da API em Python 3.13, Django 5.2 e Django REST Framework. `GET /api/v1/health/` responde `{"status":"ok","service":"labtech-api"}` e verifica apenas o processo HTTP. UC001 oferece `GET /api/v1/auth/csrf/`, `POST /api/v1/auth/login/`, `POST /api/v1/auth/logout/` e `GET /api/v1/auth/me/` com sessões Django provisórias. As apps ainda não têm models nem endpoints de domínio.

## Preparar o ambiente local

1. Instale Python 3.13 e crie um ambiente virtual:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[dev]"
   ```

   Em Linux/macOS, use `python3.13 -m venv .venv` e `source .venv/bin/activate`.

2. Copie `.env.example` para `.env` e troque `DJANGO_SECRET_KEY` por uma chave aleatória. Por exemplo, gere uma com `python -c "import secrets; print(secrets.token_urlsafe(50))"`. O arquivo `.env` é ignorado pelo Git. `DJANGO_DEBUG=true` e as origens de exemplo são apenas para desenvolvimento.

3. Mantenha `DB_NAME` vazio enquanto o contrato e o servidor PostgreSQL não estiverem disponíveis. Nesse caso, Django usa um backend dummy: o endpoint de saúde e os testes atuais funcionam, mas operações de banco não funcionam. Quando o responsável pelo banco fornecer acesso, preencha `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e `DB_PORT` no `.env`. Não execute `migrate` nesta etapa.

4. Verifique e inicie a API:

   ```powershell
   python manage.py check
   python manage.py runserver
   ```

   Acesse `http://127.0.0.1:8000/api/v1/health/`. As rotas HTTP de UC001 existem, mas login e persistência de sessão exigem banco de usuários e sessões configurado; outros endpoints de negócio ainda não existem.

## Verificações

Com o ambiente ativado e `.env` configurado:

```powershell
python -m pip check
python -m ruff check .
python -m pytest -q
python manage.py test
python manage.py check --deploy
```

`check --deploy` pode apontar pendências de HTTPS, redirecionamento e HSTS: esses controles dependem da configuração do proxy e do domínio de produção. O servidor `runserver` não é um servidor de produção.

## Docker para desenvolvimento

Com Docker ativo e `.env` criado, execute `docker compose up --build`. A API ficará em `http://localhost:8000/api/v1/health/`. A imagem executa o processo como usuário sem privilégios. O Compose não cria PostgreSQL nem aplica migrations. Se o PostgreSQL estiver na máquina hospedeira, use `DB_HOST=host.docker.internal` no `.env` para o contêiner alcançá-lo; `localhost` dentro do contêiner aponta para o próprio contêiner. Se o banco estiver em outro servidor, use o endereço fornecido pela equipe de banco.

## Integração contínua

O workflow `.github/workflows/ci.yml` roda em pull requests para `main` e em pushes na `main`. Ele instala as dependências de desenvolvimento no Python 3.13 e executa `pip check`, Ruff, `manage.py check` e pytest. Cada execução gera sua própria `DJANGO_SECRET_KEY`; `DB_NAME` fica vazio, sem PostgreSQL ou migrations na CI inicial.

## Próxima etapa

UC001 tem uma camada HTTP com sessões Django provisórias e rota pública para obter o cookie CSRF, sem schema ou migrations de usuário. A integração real de identidade, sessão e banco ainda depende de decisão. O fluxo de cookies e cabeçalho `X-CSRFToken`, além das pendências de CORS para origens distintas, estão em [docs/API_CONTRATOS_MVP.md](docs/API_CONTRATOS_MVP.md). Consulte também [docs/REQUISITOS_E_CONTRATO.md](docs/REQUISITOS_E_CONTRATO.md).

Licença: [GNU GPL v3](LICENSE).
