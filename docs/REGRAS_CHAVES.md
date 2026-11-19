# Regras de retirada e devolução de chaves (UC005 e UC006)

`apps.keys.rules` contém `register_checkout` e `register_return`. Ambas recebem um histórico de eventos em memória e devolvem uma **nova tupla**, acrescentando um evento. `KeyCheckout` e `KeyReturn` são registros imutáveis; eventos anteriores não são editados ou removidos. As funções não usam Django, ORM, PostgreSQL ou HTTP.

- Uma retirada exige referências para empréstimo, chave e responsável, além de `datetime` com timezone. As referências são identificadores opacos e hashable, sem escolha de tabela ou tipo de chave primária. `loan_ref` deve ser único em todo o histórico fornecido, inclusive após a devolução.
- Uma chave com empréstimo ativo não pode ser retirada novamente. Depois da devolução, esse bloqueio deixa de existir; uma nova retirada exige outra referência de empréstimo.
- Uma devolução identifica a retirada por `loan_ref`, exige empréstimo ativo e não pode anteceder a retirada. Uma segunda devolução do mesmo empréstimo é rejeitada. Datas/horas com fusos distintos são comparadas como instantes em UTC.
- O histórico é fornecido na ordem das operações. Os timestamps, comparados em UTC, não podem recuar nessa sequência; horários iguais são aceitos. Eventos inconsistentes ou de tipo desconhecido são rejeitados.

O chamador deve fornecer o histórico relevante e persistir a nova sequência conforme o contrato de banco futuro. As funções não definem prazos máximos, multas, autorização por perfil ou outras restrições institucionais. Também não verificam indisponibilidade física ou administrativa da chave além de um empréstimo ativo; essas regras ainda precisam ser acordadas.

**Persistência em desenvolvimento:** [MODELO_CHAVES.md](MODELO_CHAVES.md) descreve o schema e os serviços PostgreSQL. As regras puras continuam sem acesso ao banco. Responsáveis e operadores usam provisoriamente `auth.User`; permissões e restrições adicionais ainda dependem de decisão.
