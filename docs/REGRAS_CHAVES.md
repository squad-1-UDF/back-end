# Regras de retirada e devolução de chaves (UC005 e UC006)

`apps.keys.rules` contém `register_checkout` e `register_return`. Ambas recebem um histórico de eventos em memória e devolvem uma **nova tupla**, acrescentando um evento. `KeyCheckout` e `KeyReturn` são registros imutáveis; eventos anteriores não são editados ou removidos. As funções não usam Django, ORM, PostgreSQL ou HTTP.

- Uma retirada exige referências para empréstimo, chave e responsável, além de `datetime` com timezone. As referências são identificadores opacos e hashable, sem escolha de tabela ou tipo de chave primária. `loan_ref` deve ser único em todo o histórico fornecido, inclusive após a devolução.
- Uma chave com empréstimo ativo não pode ser retirada novamente. Depois da devolução, esse bloqueio deixa de existir; uma nova retirada exige outra referência de empréstimo.
- Uma devolução identifica a retirada por `loan_ref`, exige empréstimo ativo e não pode anteceder a retirada. Uma segunda devolução do mesmo empréstimo é rejeitada. Datas/horas com fusos distintos são comparadas como instantes em UTC.
- O histórico é fornecido na ordem das operações. Os timestamps, comparados em UTC, não podem recuar nessa sequência; horários iguais são aceitos. Eventos inconsistentes ou de tipo desconhecido são rejeitados.

O chamador deve fornecer o histórico relevante e persistir a nova sequência conforme o contrato de banco futuro. As funções não definem prazos máximos, multas, autorização por perfil ou outras restrições institucionais. Também não verificam indisponibilidade física ou administrativa da chave além de um empréstimo ativo; essas regras ainda precisam ser acordadas.

**Decisões pendentes:** forma das referências e vínculo do responsável com a tabela de usuários, esquema de empréstimos e movimentações, permissões, convenção de timestamps/timezone e eventuais restrições adicionais da chave. A validação em memória não impede duas retiradas concorrentes: a integração com PostgreSQL precisará de transações e constraints que garantam a exclusividade do empréstimo ativo para cada chave. Nenhuma tabela ou migration é criada nesta etapa.
