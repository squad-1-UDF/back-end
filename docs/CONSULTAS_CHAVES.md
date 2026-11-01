# Consultas de chaves (UC007 e UC008)

As funções em `apps.keys.rules` recebem um histórico de `KeyCheckout` e `KeyReturn` em memória. Elas usam o mesmo replay que valida retiradas e devoluções: referências duplicadas, devolução sem empréstimo ativo, duas retiradas ativas da mesma chave, tipos desconhecidos e horários fora de ordem são rejeitados. Nenhuma consulta altera os eventos recebidos.

- `has_active_loan(history, key_ref)` informa se a chave tem empréstimo ativo.
- `active_loan_ref_for_key(history, key_ref)` devolve a referência do empréstimo ativo ou `None` quando não há um.
- `movements_for_key(history, key_ref)` devolve uma tupla de eventos da chave na ordem original. Como `KeyReturn` contém a referência do empréstimo, a consulta associa cada devolução à `KeyCheckout` correspondente para descobrir a chave. Uma chave nunca retirada tem histórico vazio.

**Disponibilidade nesta etapa significa somente ausência de empréstimo ativo.** Uma chave pode continuar indisponível por motivos físicos ou administrativos que estas funções não conhecem. O chamador deve fornecer o histórico completo e ordenado necessário para validar as associações; uma devolução sem a retirada correspondente é um histórico inválido.

As consultas não acessam Django ORM, PostgreSQL ou HTTP. Elas não bloqueiam retiradas concorrentes nem substituem transações e constraints na persistência futura. Filtros por usuário, paginação, permissões, relatórios e formato de resposta da API dependem do contrato institucional e do esquema de banco ainda pendentes; não são definidos aqui.
