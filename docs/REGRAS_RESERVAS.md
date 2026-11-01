# Regras de horários de reservas

`apps.bookings.rules` contém funções puras para uso futuro pelo serviço de reservas:

- `validate_interval(inicio, fim)` valida o intervalo e lança `TypeError` para valores que não sejam `datetime` e `ValueError` para datetimes sem timezone, duração zero ou fim anterior ao início.
- `intervals_overlap(inicio_a, fim_a, inicio_b, fim_b)` valida ambos os intervalos e informa se eles compartilham algum instante.
- `is_available(inicio, fim, reservas)` recebe pares `(inicio, fim)` em memória, valida todos eles e retorna `True` somente quando nenhum se sobrepõe ao intervalo solicitado. A lista vazia está disponível.

Os intervalos são **[início, fim)**: incluem o início e excluem o fim. Assim, `10:00–11:00` e `11:00–12:00` são consecutivos e não conflitam. A comparação usa instantes em UTC; os valores recebidos precisam conter timezone, mas não precisam usar o mesmo fuso. Nenhum limite de duração, horário de expediente ou recorrência foi definido.

`is_available` recebe somente pares de horários: não recebe identificador de sala/laboratório nem estado da reserva. O chamador deve fornecer **apenas reservas ativas do mesmo espaço**; reservas canceladas ou de outras salas devem ser excluídas antes da chamada. Qualquer intervalo fornecido será tratado como ocupação, independentemente de sua origem.

As funções não consultam banco, não criam endpoints e não impedem que duas requisições simultâneas gravem reservas conflitantes. Na integração com PostgreSQL, a prevenção de conflitos concorrentes dependerá de transações e constraints adequadas ao esquema acordado com a equipe de banco. As regras de reserva ainda são propostas de MVP, conforme `REQUISITOS_E_CONTRATO.md`.
