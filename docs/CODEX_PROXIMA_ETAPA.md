# Instrução para Codex (fase seguinte)

Inspecione este repositório Django, o `README.md` e `docs/REQUISITOS_E_CONTRATO.md`. Não implemente models, migrations, nem crie/troque schema do PostgreSQL antes de receber o contrato do responsável pelo banco. Trabalhe em uma branch `feature/auth-api`, sem alterar arquivos não relacionados.

Primeiro, proponha um plano mínimo de implementação de UC001 (autenticação) e UC002 (usuários) conforme os requisitos, incluindo decisões pendentes sobre tabela de usuários, perfis e login por sessão ou JWT. Solicite explicitamente os detalhes de banco ainda ausentes e não invente colunas. Uma vez fornecido contrato, implemente endpoints, serializers, permissions e testes, rode `python manage.py check` e testes relevantes, e reporte comandos/resultados e limitações. Não faça `migrate` em banco compartilhado; não comite segredos.
