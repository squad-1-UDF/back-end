"""Gera a base FICTÍCIA de demonstração do LabTech (sem dados pessoais reais).

Uso:  python3 dados/gerar_dados.py      (só biblioteca padrão; resultado sempre igual)

Saídas (em dados/):
  csv/<tabela>.csv            um CSV por tabela, colunas iguais às do banco
  labtech-demo.json           todas as tabelas num JSON simples {tabela: [linhas]}
  fixture-django.json         mesmo conteúdo no formato do `manage.py loaddata`
  ../sql/dados-demo.sql       INSERTs para carregar num PostgreSQL local de teste

Todos os nomes são genéricos, e-mails usam o domínio reservado exemplo.com e as
senhas são "inutilizáveis" no padrão do Django (começam com "!"): ninguém
consegue entrar com esses usuários.

Os dados respeitam todas as regras do schema: no máximo 1 empréstimo ativo por
chave, devolução depois da retirada, 1 retirada + no máximo 1 devolução por
empréstimo, e nenhuma reserva ativa sobreposta no mesmo espaço (reservas
encostadas, como 10h–11h e 11h–12h, são válidas porque o intervalo é [início, fim)).
"""
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BRT = timezone(timedelta(hours=-3))
BASE = datetime(2026, 11, 3, 0, 0, tzinfo=BRT)  # segunda-feira
AGORA = datetime(2026, 11, 21, 9, 0, tzinfo=BRT)
rnd = random.Random(2026)


def iso(dt):
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# auth_user
# ---------------------------------------------------------------------------
PESSOAS = [
    # username, first, last, is_staff  (operadores do balcão são staff)
    ("operador.1", "Operador", "Teste 1", True),
    ("operador.2", "Operador", "Teste 2", True),
    ("coordenacao", "Coordenação", "Teste", True),
    ("professor.1", "Professor", "Teste 1", False),
    ("professor.2", "Professor", "Teste 2", False),
    ("professor.3", "Professor", "Teste 3", False),
    ("professor.4", "Professor", "Teste 4", False),
    ("aluno.1", "Aluno", "Teste 1", False),
    ("aluno.2", "Aluno", "Teste 2", False),
    ("aluno.3", "Aluno", "Teste 3", False),
    ("aluno.4", "Aluno", "Teste 4", False),
    ("aluno.5", "Aluno", "Teste 5", False),
]
usuarios = []
for i, (login, nome, sobrenome, staff) in enumerate(PESSOAS, start=1):
    usuarios.append({
        "id": i, "password": "!demo-sem-login", "last_login": None, "is_superuser": False,
        "username": login, "first_name": nome, "last_name": sobrenome,
        "email": f"{login}@exemplo.com", "is_staff": staff, "is_active": True,
        "date_joined": iso(datetime(2026, 11, 1, 8, 0, tzinfo=BRT)),
    })
OPERADORES = [u["id"] for u in usuarios if u["is_staff"]]
RESPONSAVEIS = [u["id"] for u in usuarios if not u["is_staff"]]
PROFESSORES = [u["id"] for u in usuarios if u["username"].startswith("professor")]

# ---------------------------------------------------------------------------
# spaces_space
# ---------------------------------------------------------------------------
ESPACOS = [("LAB-01", "laboratory"), ("LAB-02", "laboratory"), ("LAB-03", "laboratory"),
           ("LAB-REDES", "laboratory"), ("SALA-101", "room"), ("SALA-102", "room"),
           ("SALA-201", "room"), ("SALA-202", "room"), ("AUDITORIO", "room"), ("SALA-REUNIAO", "room")]
espacos = [{"id": i, "code": c, "kind": k} for i, (c, k) in enumerate(ESPACOS, start=1)]

# ---------------------------------------------------------------------------
# keys_key  (laboratórios têm 2 cópias; a sala de reunião ainda não tem chave)
# ---------------------------------------------------------------------------
chaves = []
for e in espacos:
    copias = 2 if e["kind"] == "laboratory" else (0 if e["code"] == "SALA-REUNIAO" else 1)
    for _ in range(copias):
        chaves.append({"id": len(chaves) + 1, "space_id": e["id"]})

# ---------------------------------------------------------------------------
# keys_keyloan + keys_keymovement
# ---------------------------------------------------------------------------
emprestimos, movimentos = [], []
livre_desde = {c["id"]: BASE for c in chaves}  # garante que não há 2 ativos por chave


def novo_emprestimo(chave_id, retirada, devolucao):
    emp_id = len(emprestimos) + 1
    op_saida = rnd.choice(OPERADORES)
    op_volta = rnd.choice(OPERADORES) if devolucao else None
    emprestimos.append({
        "id": emp_id, "checked_out_at": iso(retirada), "returned_at": iso(devolucao),
        "checkout_operator_id": op_saida, "key_id": chave_id,
        "responsible_id": rnd.choice(RESPONSAVEIS), "return_operator_id": op_volta,
    })
    movimentos.append({"id": len(movimentos) + 1, "kind": "checkout", "occurred_at": iso(retirada),
                       "loan_id": emp_id, "operator_id": op_saida})
    if devolucao:
        movimentos.append({"id": len(movimentos) + 1, "kind": "return", "occurred_at": iso(devolucao),
                           "loan_id": emp_id, "operator_id": op_volta})


# 34 empréstimos já devolvidos, em dias úteis das últimas 3 semanas
for _ in range(34):
    for _tentativa in range(50):
        chave = rnd.choice(chaves)["id"]
        dia = BASE + timedelta(days=rnd.choice([d for d in range(18) if (BASE + timedelta(days=d)).weekday() < 5]))
        retirada = dia + timedelta(hours=rnd.choice([7, 8, 9, 10, 13, 14, 15, 18, 19]), minutes=rnd.choice([0, 5, 10, 20, 30]))
        devolucao = retirada + timedelta(minutes=rnd.choice([50, 90, 100, 110, 180, 220]))
        if retirada >= livre_desde[chave] and devolucao < AGORA:
            livre_desde[chave] = devolucao
            novo_emprestimo(chave, retirada, devolucao)
            break
# ordena por horário de retirada (ids crescentes no tempo, como no uso real)
emprestimos.sort(key=lambda e: e["checked_out_at"])
mapa = {}
for novo_id, e in enumerate(emprestimos, start=1):
    mapa[e["id"]] = novo_id
    e["id"] = novo_id
for m in movimentos:
    m["loan_id"] = mapa[m["loan_id"]]
movimentos.sort(key=lambda m: (m["occurred_at"], m["kind"] != "checkout"))
for novo_id, m in enumerate(movimentos, start=1):
    m["id"] = novo_id

# 3 empréstimos ATIVOS agora (chaves diferentes, retiradas depois da última devolução de cada uma)
ativos = [c["id"] for c in chaves if livre_desde[c["id"]] < AGORA - timedelta(hours=2)][:3]
for chave, horas in zip(ativos, (0.5, 1, 1.5)):
    novo_emprestimo(chave, AGORA - timedelta(hours=horas), None)

# ---------------------------------------------------------------------------
# bookings_booking (sem sobreposição ATIVA no mesmo espaço)
# ---------------------------------------------------------------------------
reservas = []
ocupado = {e["id"]: [] for e in espacos}


def cabe(espaco, ini, fim):
    return all(fim <= a or ini >= b for a, b in ocupado[espaco])  # [início, fim)


dias = [AGORA.replace(hour=0, minute=0) + timedelta(days=d) for d in range(-7, 10)]
dias = [d for d in dias if d.weekday() < 5]
while len(reservas) < 30:
    espaco = rnd.choice(espacos[:9])["id"]
    dia = rnd.choice(dias)
    ini = dia + timedelta(hours=rnd.choice([8, 9, 10, 11, 13, 14, 15, 16, 19]))
    fim = ini + timedelta(hours=rnd.choice([1, 1, 2]))
    if not cabe(espaco, ini, fim):
        continue
    ocupado[espaco].append((ini, fim))
    criada = min(ini - timedelta(days=rnd.randint(1, 5), hours=rnd.randint(0, 6)), AGORA - timedelta(hours=1))
    reservas.append({"id": 0, "start_at": iso(ini), "end_at": iso(fim), "status": "active",
                     "created_at": iso(criada), "cancelled_at": None, "space_id": espaco,
                     "user_id": rnd.choice(PROFESSORES + RESPONSAVEIS[:2])})

# Caso didático 1: reservas ENCOSTADAS no LAB-01 (10h–11h e 11h–12h) — válidas
dia_demo = datetime(2026, 11, 24, 0, 0, tzinfo=BRT)
for h in (10, 11):
    ini, fim = dia_demo + timedelta(hours=h), dia_demo + timedelta(hours=h + 1)
    if cabe(1, ini, fim):
        ocupado[1].append((ini, fim))
        reservas.append({"id": 0, "start_at": iso(ini), "end_at": iso(fim), "status": "active",
                         "created_at": iso(AGORA - timedelta(days=1)), "cancelled_at": None,
                         "space_id": 1, "user_id": PROFESSORES[0]})
# Caso didático 2: reserva CANCELADA sobreposta a uma ativa — válida (a regra só vale para ativas)
ini, fim = dia_demo + timedelta(hours=10, minutes=30), dia_demo + timedelta(hours=11, minutes=30)
reservas.append({"id": 0, "start_at": iso(ini), "end_at": iso(fim), "status": "cancelled",
                 "created_at": iso(AGORA - timedelta(days=2)), "cancelled_at": iso(AGORA - timedelta(days=1, hours=3)),
                 "space_id": 1, "user_id": PROFESSORES[1]})
# mais 3 canceladas comuns
for r in rnd.sample([r for r in reservas if r["status"] == "active" and r["space_id"] != 1], 3):
    r["status"] = "cancelled"
    r["cancelled_at"] = iso(datetime.fromisoformat(r["created_at"]) + timedelta(hours=5))
reservas.sort(key=lambda r: (r["created_at"], r["start_at"]))
for i, r in enumerate(reservas, start=1):
    r["id"] = i

# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------
TABELAS = {
    "auth_user": usuarios, "spaces_space": espacos, "keys_key": chaves,
    "keys_keyloan": emprestimos, "keys_keymovement": movimentos, "bookings_booking": reservas,
}
MODELOS = {"auth_user": "auth.user", "spaces_space": "spaces.space", "keys_key": "keys.key",
           "keys_keyloan": "keys.keyloan", "keys_keymovement": "keys.keymovement",
           "bookings_booking": "bookings.booking"}

(RAIZ / "csv").mkdir(exist_ok=True)
for nome, linhas in TABELAS.items():
    with open(RAIZ / "csv" / f"{nome}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        for l in linhas:
            w.writerow({k: ("" if v is None else v) for k, v in l.items()})

with open(RAIZ / "labtech-demo.json", "w", encoding="utf-8") as f:
    json.dump({"_sobre": "Dados fictícios de demonstração do LabTech. Sem dados pessoais reais.",
               **TABELAS}, f, ensure_ascii=False, indent=2)


def campo_fixture(nome, k):
    return k[:-3] if k.endswith("_id") and nome != "auth_user" else k


fixture = []
for nome, linhas in TABELAS.items():
    for l in linhas:
        campos = {campo_fixture(nome, k): v for k, v in l.items() if k != "id"}
        if nome == "auth_user":
            campos.update(groups=[], user_permissions=[])
        fixture.append({"model": MODELOS[nome], "pk": l["id"], "fields": campos})
with open(RAIZ / "fixture-django.json", "w", encoding="utf-8") as f:
    json.dump(fixture, f, ensure_ascii=False, indent=2)


def sql_valor(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


with open(RAIZ.parent / "sql" / "dados-demo.sql", "w", encoding="utf-8") as f:
    f.write("-- Dados fictícios do LabTech (gerado por dados/gerar_dados.py). Carregar só em banco local de teste.\n")
    f.write("BEGIN;\n")
    for nome, linhas in TABELAS.items():
        cols = list(linhas[0])
        f.write(f"\n-- {nome} ({len(linhas)} linhas)\n")
        for l in linhas:
            f.write(f"INSERT INTO {nome} ({', '.join(cols)}) OVERRIDING SYSTEM VALUE VALUES "
                    f"({', '.join(sql_valor(l[c]) for c in cols)});\n")
    f.write("\n-- Ajusta as sequências de id para continuar depois dos dados de exemplo\n")
    for nome in TABELAS:
        f.write(f"SELECT setval(pg_get_serial_sequence('{nome}', 'id'), (SELECT max(id) FROM {nome}));\n")
    f.write("COMMIT;\n")

for nome, linhas in TABELAS.items():
    print(f"{nome:18} {len(linhas):3} linhas")
