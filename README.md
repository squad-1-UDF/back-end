# Sistema de Gestão de Laboratórios e Salas — API

Scaffold da API em Python 3.13, Django 5.2 e Django REST Framework. Esta etapa oferece apenas `GET /api/v1/health/`, que responde `{"status":"ok","service":"labtech-api"}`. O endpoint verifica o processo HTTP, não a conexão com o banco. As apps `accounts`, `spaces`, `keys` e `bookings` ainda não têm models nem endpoints de domínio.

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

   Acesse `http://127.0.0.1:8000/api/v1/health/`. Outros endpoints de negócio ainda não existem.

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

## Próxima etapa

UC001 (login) depende da definição conjunta de tabela de usuários, perfis e mecanismo de autenticação (sessão ou token). O contrato proposto e as decisões pendentes estão em [docs/REQUISITOS_E_CONTRATO.md](docs/REQUISITOS_E_CONTRATO.md). Não há schema ou migrations de domínio nesta branch.

Licença: [GNU GPL v3](LICENSE).
