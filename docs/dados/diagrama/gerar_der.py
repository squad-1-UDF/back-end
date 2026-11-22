"""Gera diagrama/DER-LabTech.drawio (DER do LabTech, squad-1-UDF/back-end @ ee65ad3).

Uso (na pasta labtech-dados):
    python3 diagrama/gerar_der.py
    drawio --export --format png --scale 2.5 --border 24 -o diagrama/DER-LabTech.png diagrama/DER-LabTech.drawio
    drawio --export --format svg --border 24 -o diagrama/DER-LabTech.svg diagrama/DER-LabTech.drawio

Fonte das colunas: sql/schema-labtech.sql (reconstrução fiel das migrations do main).
Status visual:
  - tabela com borda contínua  = implementada (auth_user, spaces_space)
  - tabela com borda tracejada + selo "EM DESENVOLVIMENTO" = já tem migration no main
    (19/11), mas o contrato ainda está em validação (Key, KeyLoan, KeyMovement, Booking)
  - linha em itálico com marcador PROP = campo PROPOSTO, não existe no código

Todas as rotas são ortogonais e calculadas aqui. Antes de gravar, o script verifica
que nenhuma linha atravessa tabela ou selo, que nenhuma linha cruza outra e que nenhum
rótulo encosta em linha ou tabela (falha com erro se houver).
"""
import os
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

PASTA = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
FONTE = "Helvetica"

W, HDR, ROW = 380, 46, 24
COLS = (60, 172, 116, 32)  # marcador, coluna, tipo, NN
PAD = 30

CORES = {  # fundo grupo, borda grupo, título grupo, cabeçalho tabela, borda tabela
    "salas": ("#F3F9F5", "#CFE5D6", "#2E7D4F", "#D7EEDF", "#7FB894"),
    "chaves": ("#F2F6FC", "#CCD9EE", "#2F5E9E", "#DCE7F7", "#6F92C8"),
    "reservas": ("#FFF8F1", "#F1D9C0", "#B45309", "#FCE6D0", "#D99A5E"),
    "usuarios": ("#F7F3FB", "#DDD1EA", "#6B4C8C", "#E8DDF2", "#A68CC1"),
}
TINTA, TINTA2, TINTA3 = "#1F2933", "#52606D", "#7B8794"
LINHA = "#4A5563"
PK_FUNDO = "#FFF6D6"
PROP_FUNDO, PROP_COR = "#F6F7F9", "#0F766E"
SEPARADOR = "#E7EAEE"
SELO = ("#FFF4E5", "#E9B45E", "#9A5B00")  # fundo, borda, texto

TZ = "timestamptz"
DEV, IMPL = "dev", "impl"
# nome: (grupo, status, x, y, título, descrição, [(marcadores, coluna, tipo, NOT NULL)])
TABELAS = {
    "spaces_space": ("salas", IMPL, 140, 180, "spaces_space", "Salas e laboratórios — Space", [
        ("PK", "id", "bigint", 1), ("UQ CK", "code", "varchar(50)", 1), ("CK", "kind", "varchar(10)", 1),
        ("PROP", "name", "varchar(100)", 1), ("PROP", "location", "varchar(120)", 0),
        ("PROP", "capacity", "integer", 0), ("PROP", "is_active", "boolean", 1)]),
    "keys_key": ("chaves", DEV, 140, 490, "keys_key", "Chave física — Key", [
        ("PK", "id", "bigint", 1), ("FK", "space_id", "bigint", 1),
        ("PROP", "label", "varchar(30)", 1), ("PROP", "status", "varchar(12)", 1)]),
    "bookings_booking": ("reservas", DEV, 140, 738, "bookings_booking", "Reserva de sala/laboratório — Booking", [
        ("PK", "id", "bigint", 1), ("FK EX", "space_id", "bigint", 1), ("FK", "user_id", "integer", 1),
        ("CK EX", "start_at", TZ, 1), ("CK EX", "end_at", TZ, 1), ("CK EX", "status", "varchar(9)", 1),
        ("", "created_at", TZ, 1), ("CK", "cancelled_at", TZ, 0)]),
    "keys_keyloan": ("chaves", DEV, 720, 180, "keys_keyloan", "Empréstimo de chave — KeyLoan", [
        ("PK", "id", "bigint", 1), ("FK UQ¹", "key_id", "bigint", 1), ("FK", "responsible_id", "integer", 1),
        ("FK", "checkout_operator_id", "integer", 1), ("FK CK", "return_operator_id", "integer", 0),
        ("CK", "checked_out_at", TZ, 1), ("UQ¹ CK", "returned_at", TZ, 0),
        ("PROP", "expected_return_at", TZ, 0)]),
    "keys_keymovement": ("chaves", DEV, 720, 500, "keys_keymovement", "Retirada / devolução — KeyMovement", [
        ("PK", "id", "bigint", 1), ("FK UQ²", "loan_id", "bigint", 1), ("CK UQ²", "kind", "varchar(8)", 1),
        ("", "occurred_at", TZ, 1), ("FK", "operator_id", "integer", 1)]),
    "auth_user": ("usuarios", IMPL, 1400, 480, "auth_user", "Usuários — auth.User do Django", [
        ("PK", "id", "integer", 1), ("UQ", "username", "varchar(150)", 1), ("", "first_name", "varchar(150)", 1),
        ("", "last_name", "varchar(150)", 1), ("", "email", "varchar(254)", 1), ("", "is_staff", "boolean", 1),
        ("", "is_active", "boolean", 1), ("", "date_joined", TZ, 1),
        ("+", "+ demais campos do Django (password, last_login, is_superuser)", "", 0)]),
}

# Grupos: (id, grupo, título, subtítulo, x, y, largura, altura)
GRUPOS = [
    ("g_salas", "salas", "Salas e laboratórios", "UC003 · implementado", 50, 118, 520, 300),
    ("g_chaves_a", "chaves", "Chaves", "UC004 · em desenvolvimento", 50, 428, 520, 228),
    ("g_reservas", "reservas", "Reservas", "agenda · em desenvolvimento", 50, 676, 520, 324),
    ("g_chaves_b", "chaves", "Empréstimos e movimentações", "UC005–UC008 · em desenvolvimento", 680, 118, 460, 572),
    ("g_usuarios", "usuarios", "Usuários", "UC001/UC002 · implementado", 1360, 418, 460, 348),
]

SELO_W, SELO_H = 128, 17


def altura(t):
    return HDR + ROW * len(TABELAS[t][6])


def ret(t):
    _, _, x, y, _, _, _ = TABELAS[t]
    return x, y, x + W, y + altura(t)


def ylin(t, col):
    _, _, _, y, _, _, cols = TABELAS[t]
    return y + HDR + ROW * [c[1] for c in cols].index(col) + ROW / 2


def nn(t, col):
    return next(c[3] for c in TABELAS[t][6] if c[1] == col)


def selo(t):
    x0, y0, x1, _ = ret(t)
    return (x1 - SELO_W, y0 - SELO_H - 4, x1, y0 - 4)


def obstaculos():
    obs = {t: ret(t) for t in TABELAS}
    for t, v in TABELAS.items():
        if v[1] == DEV:
            obs[f"selo:{t}"] = selo(t)
    return obs


# ---------------------------------------------------------------------------
# Relações. ap = âncora no pai: ("lin", lado, coluna) | ("borda", lado, x|y)
#           filho: col = coluna FK (entra pela lateral lf) ou entra=("T"|"B", x)
# ---------------------------------------------------------------------------
Y_KEY_HDR = ret("keys_key")[1] + HDR / 2
AUTH_TOPO = ret("auth_user")[1]
AUTH_BASE = ret("auth_user")[3]
Y_BAIXO = 1030

RELACOES = [
    dict(pai="spaces_space", ap=("borda", "B", 330), filho="keys_key", col="space_id", entra=("T", 330),
         via=[], verbo="possui", rot=(330, 442), rot_lado="vert"),
    dict(pai="spaces_space", ap=("lin", "L", "id"), filho="bookings_booking", col="space_id", lf="L",
         via=[(66, ylin("spaces_space", "id")), (66, ylin("bookings_booking", "space_id"))],
         verbo="é reservado", rot=(66, 666), rot_lado="vert"),
    dict(pai="keys_key", ap=("borda", "R", Y_KEY_HDR), filho="keys_keyloan", col="key_id", lf="L",
         via=[(625, Y_KEY_HDR), (625, ylin("keys_keyloan", "key_id"))],
         verbo="é emprestada", rot=(672, ylin("keys_keyloan", "key_id") - 12)),
    dict(pai="keys_keyloan", ap=("borda", "B", 770), filho="keys_keymovement", col="loan_id", lf="L",
         via=[(770, 460), (700, 460), (700, ylin("keys_keymovement", "loan_id"))],
         verbo="registra", rot=(735, 448)),
    # Usuários -> empréstimo (três papéis), saindo do topo de auth_user
    dict(pai="auth_user", ap=("borda", "T", 1762), filho="keys_keyloan", col="responsible_id", lf="R",
         via=[(1762, ylin("keys_keyloan", "responsible_id"))],
         verbo="responsável (responsible)", rot=(1250, ylin("keys_keyloan", "responsible_id") - 12)),
    dict(pai="auth_user", ap=("borda", "T", 1734), filho="keys_keyloan", col="checkout_operator_id", lf="R",
         via=[(1734, ylin("keys_keyloan", "checkout_operator_id"))],
         verbo="registra a retirada (checkout_operator)",
         rot=(1300, ylin("keys_keyloan", "checkout_operator_id") - 12)),
    dict(pai="auth_user", ap=("borda", "T", 1706), filho="keys_keyloan", col="return_operator_id", lf="R",
         via=[(1706, ylin("keys_keyloan", "return_operator_id"))],
         verbo="registra a devolução (return_operator)",
         rot=(1300, ylin("keys_keyloan", "return_operator_id") - 12)),
    dict(pai="auth_user", ap=("lin", "L", "id"), filho="keys_keymovement", col="operator_id", lf="R",
         via=[(1190, ylin("auth_user", "id")), (1190, ylin("keys_keymovement", "operator_id"))],
         verbo="opera (operator)", rot=(1190, 596), rot_lado="vert"),
    dict(pai="auth_user", ap=("borda", "B", 1460), filho="bookings_booking", col="user_id", lf="R",
         via=[(1460, Y_BAIXO), (600, Y_BAIXO), (600, ylin("bookings_booking", "user_id"))],
         verbo="faz a reserva (user)", rot=(1030, Y_BAIXO - 12)),
]


def ponto_pai(r):
    tipo, lado, v = r["ap"]
    x0, y0, x1, y1 = ret(r["pai"])
    if tipo == "lin":
        return (x0 if lado == "L" else x1, ylin(r["pai"], v))
    if lado in ("T", "B"):
        return (v, y0 if lado == "T" else y1)
    return (x0 if lado == "L" else x1, v)


def ponto_filho(r):
    x0, y0, x1, y1 = ret(r["filho"])
    if "entra" in r:
        lado, v = r["entra"]
        return (v, y0 if lado == "T" else y1)
    return (x0 if r["lf"] == "L" else x1, ylin(r["filho"], r["col"]))


def caminho(r):
    return [ponto_pai(r)] + r["via"] + [ponto_filho(r)]


def opcional(r):
    return not nn(r["filho"], r["col"])


FONTE_ROT = 11


def caixa_rotulo(r):
    w = 5.6 * len(r["verbo"]) + 6
    h = 16
    x, y = r["rot"]
    if r.get("rot_lado") == "vert":
        return (x + 7, y - h / 2, x + 7 + w, y + h / 2)
    if r.get("rot_lado") == "vertL":
        return (x - 7 - w, y - h / 2, x - 7, y + h / 2)
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


# ---------------------------------------------------------------------------
# Conferência geométrica
# ---------------------------------------------------------------------------
def segmentos(pts):
    return list(zip(pts, pts[1:]))


def cruza(a, b):
    (p1, p2), (q1, q2) = a, b
    ax0, ax1 = sorted((p1[0], p2[0])); ay0, ay1 = sorted((p1[1], p2[1]))
    bx0, bx1 = sorted((q1[0], q2[0])); by0, by1 = sorted((q1[1], q2[1]))
    return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1


def seg_em_ret(s, rc, folga=0.5):
    (p1, p2) = s
    x0, y0, x1, y1 = rc
    sx0, sx1 = sorted((p1[0], p2[0])); sy0, sy1 = sorted((p1[1], p2[1]))
    return sx0 < x1 - folga and sx1 > x0 + folga and sy0 < y1 - folga and sy1 > y0 + folga


def conferir():
    erros = []
    obs = obstaculos()
    caminhos = {i: caminho(r) for i, r in enumerate(RELACOES)}
    for i, pts in caminhos.items():
        for a, b in segmentos(pts):
            if a[0] != b[0] and a[1] != b[1]:
                erros.append(f"rel {i} tem trecho diagonal {a}->{b}")
            for t, rc in obs.items():
                if seg_em_ret((a, b), rc):
                    erros.append(f"rel {i} atravessa {t}")
    for i in caminhos:
        for j in caminhos:
            if j <= i:
                continue
            # duas relações podem compartilhar só o ponto de saída do mesmo pai
            for s in segmentos(caminhos[i]):
                for u in segmentos(caminhos[j]):
                    if cruza(s, u):
                        erros.append(f"rel {i} ({RELACOES[i]['verbo']}) cruza rel {j} ({RELACOES[j]['verbo']})")
    for i, r in enumerate(RELACOES):
        cx = caixa_rotulo(r)
        for t, rc in obs.items():
            if seg_em_ret(((cx[0], cx[1]), (cx[2], cx[3])), rc, folga=-4):
                erros.append(f"rótulo '{r['verbo']}' encosta em {t}")
        for j, pts in caminhos.items():
            for s in segmentos(pts):
                if seg_em_ret(s, (cx[0] - 2, cx[1] - 2, cx[2] + 2, cx[3] + 2), folga=0):
                    erros.append(f"rótulo '{r['verbo']}' encosta na rel {j}")
    for g in GRUPOS:  # títulos de grupo não podem ser cortados por linhas
        _, _, tit, sub, x, y, w, h = g
        caixa = (x + PAD - 4, y + 8, x + PAD + 7.5 * max(len(tit), len(sub)) + 4, y + 47)
        for j, pts in caminhos.items():
            for s in segmentos(pts):
                if seg_em_ret(s, caixa, folga=0):
                    erros.append(f"rel {j} corta o título do grupo '{tit}'")
    return erros


# ---------------------------------------------------------------------------
# draw.io
# ---------------------------------------------------------------------------
def q(s):
    return escape(s, {'"': "&quot;"})


def gerar_drawio():
    cel = []
    add = cel.append

    def texto(id_, html, x, y, w, h, estilo=""):
        add(f'<mxCell id="{id_}" value="{q(html)}" style="text;html=1;whiteSpace=wrap;fontFamily={FONTE};'
            f'strokeColor=none;fillColor=none;{estilo}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    texto("titulo", "LabTech — Diagrama Entidade-Relacionamento (DER)", 50, 26, 1400, 36,
          f"fontSize=28;fontStyle=1;fontColor={TINTA};align=left;verticalAlign=middle;spacing=0;")
    texto("subtitulo",
          "Fonte: squad-1-UDF/back-end @ ee65ad3 · PostgreSQL 16 · 6 tabelas (auth, spaces, keys, bookings). "
          "<b>Tracejado</b> = em desenvolvimento: já possuem migration no main (19/11), contrato ainda em validação. "
          "<i>PROP</i> = campo proposto, ainda não existe no código.",
          50, 66, 1770, 40, f"fontSize=13;fontColor={TINTA2};align=left;verticalAlign=top;spacing=0;")

    for gid, g, tit, sub, x, y, w, h in GRUPOS:
        fundo, borda, cor_tit, _, _ = CORES[g]
        add(f'<mxCell id="{gid}" value="" style="rounded=1;arcSize=2;absoluteArcSize=1;html=1;'
            f'fillColor={fundo};strokeColor={borda};strokeWidth=1;" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        texto(f"{gid}_titulo", escape(tit.upper()), x + PAD, y + 10, 330, 20,
              f"fontSize=14;fontStyle=1;fontColor={cor_tit};align=left;verticalAlign=middle;spacing=0;")
        texto(f"{gid}_sub", escape(sub), x + PAD, y + 29, 330, 16,
              f"fontSize=11;fontColor={TINTA3};align=left;verticalAlign=middle;spacing=0;")

    for n, r in enumerate(RELACOES):
        pts = caminho(r)
        p0, p1 = pts[0], pts[-1]
        tp, lado, v = r["ap"]
        if tp == "lin":
            src = f'{r["pai"]}.{v}'
            ex, ey = (0 if lado == "L" else 1), 0.5
        else:
            src = r["pai"]
            x0, y0, x1, y1 = ret(r["pai"])
            ex, ey = (p0[0] - x0) / W, (p0[1] - y0) / (y1 - y0)
        if "entra" in r:
            tgt = r["filho"]
            x0, y0, x1, y1 = ret(r["filho"])
            nx, ny = (p1[0] - x0) / W, (p1[1] - y0) / (y1 - y0)
        else:
            tgt = f'{r["filho"]}.{r["col"]}'
            nx, ny = (0 if r["lf"] == "L" else 1), 0.5
        inicio = "ERzeroToOne" if opcional(r) else "ERmandOne"
        meio = "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in r["via"])
        add(f'<mxCell id="rel{n}" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
            f'html=1;strokeColor={LINHA};strokeWidth=1.4;startArrow={inicio};endArrow=ERzeroToMany;'
            f'startFill=0;endFill=0;startSize=11;endSize=11;jettySize=auto;'
            f'exitX={ex:.6f};exitY={ey:.6f};exitDx=0;exitDy=0;exitPerimeter=0;'
            f'entryX={nx:.6f};entryY={ny:.6f};entryDx=0;entryDy=0;entryPerimeter=0;" edge="1" parent="1" '
            f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry">'
            f'<Array as="points">{meio}</Array></mxGeometry></mxCell>')
        cx = caixa_rotulo(r)
        al = {"vert": "left", "vertL": "right"}.get(r.get("rot_lado"), "center")
        texto(f"rel{n}_verbo", escape(r["verbo"]), cx[0], cx[1], cx[2] - cx[0], cx[3] - cx[1],
              f"fontSize={FONTE_ROT};fontStyle=2;fontColor={TINTA2};align={al};verticalAlign=middle;spacing=0;")

    for nome, (g, status, x, y, tit, desc, cols) in TABELAS.items():
        _, _, _, cab, borda = CORES[g]
        h = altura(nome)
        dev = status == DEV
        traco = "dashed=1;dashPattern=6 4;" if dev else ""
        titulo = (f'<b style="font-size:14px;color:{TINTA}">{tit}</b><br>'
                  f'<i style="font-size:11px;color:{TINTA2}">{escape(desc)}</i>')
        add(f'<mxCell id="{nome}" value="{q(titulo)}" style="shape=table;startSize={HDR};container=1;'
            f'collapsible=0;childLayout=tableLayout;fixedRows=1;rowLines=0;columnLines=0;resizeLast=1;html=1;'
            f'whiteSpace=wrap;align=center;verticalAlign=middle;fontFamily={FONTE};fillColor={cab};'
            f'strokeColor={borda};strokeWidth={1.6 if dev else 1.2};{traco}swimlaneFillColor=#FFFFFF;'
            f'rounded=0;shadow=0;" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{W}" height="{h}" as="geometry"/></mxCell>')
        if dev:
            sx0, sy0, sx1, sy1 = selo(nome)
            add(f'<mxCell id="{nome}_selo" value="EM DESENVOLVIMENTO" style="rounded=1;arcSize=30;html=1;'
                f'fontFamily={FONTE};fontSize=9;fontStyle=1;fontColor={SELO[2]};fillColor={SELO[0]};'
                f'strokeColor={SELO[1]};spacing=0;" vertex="1" parent="1">'
                f'<mxGeometry x="{sx0}" y="{sy0}" width="{sx1 - sx0}" height="{sy1 - sy0}" as="geometry"/>'
                f'</mxCell>')
        for i, (k, c, tp, obrig) in enumerate(cols):
            rid = f"{nome}.{c}" if k != "+" else f"{nome}.mais"
            pk, prop = k == "PK", k == "PROP"
            fundo = PK_FUNDO if pk else (PROP_FUNDO if prop else "none")
            sep = "dashed=1;dashPattern=3 3;" if prop else ""
            add(f'<mxCell id="{rid}" value="" style="shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;'
                f'swimlaneBody=0;fillColor={fundo};collapsible=0;dropTarget=0;points=[[0,0.5],[1,0.5]];'
                f'portConstraint=eastwest;top={0 if i == 0 else 1};left=0;right=0;bottom=0;{sep}'
                f'strokeColor={SEPARADOR};" vertex="1" parent="{nome}">'
                f'<mxGeometry y="{HDR + ROW * i}" width="{W}" height="{ROW}" as="geometry"/></mxCell>')
            if k == "+":
                vals = [(c, f"fontSize=11;fontStyle=2;fontColor={TINTA3};align=left;spacingLeft=10;"
                            "overflow=visible;whiteSpace=nowrap;"), ("", ""), ("", ""), ("", "")]
            elif prop:
                vals = [("PROP", f"fontSize=9;fontStyle=1;align=center;fontColor={PROP_COR};"),
                        (c, f"fontSize=12;fontStyle=2;align=left;spacingLeft=6;fontColor={TINTA3};"),
                        (tp, f"fontSize=11;fontStyle=2;align=left;spacingLeft=6;fontColor={TINTA3};fontFamily=Menlo;"),
                        ("NN" if obrig else "", f"fontSize=9;fontStyle=1;align=center;fontColor=#A9B1BB;")]
            else:
                peso = 1 if pk else 0
                marc = f"fontSize=10;fontStyle=1;align=center;fontColor={'#9A6B00' if pk else TINTA2};"
                nomec = (f"fontSize=12;fontStyle={peso | (4 if 'FK' in k else 0)};align=left;spacingLeft=6;"
                         f"fontColor={TINTA};")
                tipo = f"fontSize=11;align=left;spacingLeft=6;fontColor={TINTA3};fontFamily=Menlo;"
                nnc = f"fontSize=9;fontStyle=1;align=center;fontColor={TINTA3};"
                vals = [(k, marc), (c, nomec), (tp, tipo), ("NN" if obrig else "", nnc)]
            xs = 0
            for j, ((txt, est), larg) in enumerate(zip(vals, COLS)):
                ff = "" if "fontFamily" in est else f"fontFamily={FONTE};"
                add(f'<mxCell id="{rid}#{j}" value="{q(txt)}" style="shape=partialRectangle;connectable=0;'
                    f'fillColor=none;top=0;left=0;bottom=0;right=0;verticalAlign=middle;overflow=hidden;html=1;'
                    f'{ff}{est}" vertex="1" parent="{rid}">'
                    f'<mxGeometry x="{xs}" width="{larg}" height="{ROW}" as="geometry">'
                    f'<mxRectangle width="{larg}" height="{ROW}" as="alternateBounds"/></mxGeometry></mxCell>')
                xs += larg

    gerar_legenda(add, texto)

    corpo = "".join(cel)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="app.diagrams.net" agent="diagrama/gerar_der.py" version="24.7.17">\n'
        '  <diagram id="der-labtech" name="DER LabTech">\n'
        '    <mxGraphModel dx="1900" dy="1400" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
        'arrows="1" fold="1" page="0" pageScale="1" pageWidth="1860" pageHeight="1460" '
        'background="#FFFFFF" math="0" shadow="0">\n'
        f'      <root><mxCell id="0"/><mxCell id="1" parent="0"/>{corpo}</root>\n'
        '    </mxGraphModel>\n  </diagram>\n</mxfile>\n'
    )


LEG_Y, LEG_H = 1064, 352


def gerar_legenda(add, texto):
    def cartao(id_, x, w):
        add(f'<mxCell id="{id_}" value="" style="rounded=1;arcSize=2;absoluteArcSize=1;html=1;'
            f'fillColor=#FAFBFC;strokeColor=#D9DEE4;" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{LEG_Y}" width="{w}" height="{LEG_H}" as="geometry"/></mxCell>')

    def chip(id_, txt, x, y, cor=TINTA2, fundo="#FFFFFF", w=40):
        add(f'<mxCell id="{id_}" value="{q(txt)}" style="rounded=1;arcSize=20;html=1;fontFamily={FONTE};'
            f'fontSize=10;fontStyle=1;fontColor={cor};fillColor={fundo};strokeColor=#D9DEE4;" vertex="1" '
            f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="19" as="geometry"/></mxCell>')

    est_txt = f"fontSize=12;fontColor={TINTA};align=left;verticalAlign=middle;spacing=0;"
    est_peq = f"fontSize=11;fontColor={TINTA2};align=left;verticalAlign=middle;spacing=0;"

    # Cartão 1: como ler
    x, w = 50, 560
    cartao("leg_notacao", x, w)
    texto("leg_notacao_tit", f'<b style="font-size:14px;color:{TINTA}">Como ler</b>', x + 24, LEG_Y + 16, 300, 20,
          "align=left;verticalAlign=middle;spacing=0;")
    exemplos = [
        ("ERmandOne", "<b>exatamente 1</b> → 0..N &nbsp;<span style='color:#7B8794'>FK obrigatória (NOT NULL)</span>"),
        ("ERzeroToOne", "<b>0 ou 1</b> → 0..N &nbsp;<span style='color:#7B8794'>FK opcional (aceita NULL)</span>"),
    ]
    for i, (ini, txt) in enumerate(exemplos):
        yy = LEG_Y + 56 + i * 28
        add(f'<mxCell id="leg_ex{i}" value="" style="edgeStyle=none;html=1;strokeColor={LINHA};strokeWidth=1.4;'
            f'startArrow={ini};endArrow=ERzeroToMany;startFill=0;endFill=0;startSize=11;endSize=11;" '
            f'edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{x + 24}" y="{yy}" as="sourcePoint"/><mxPoint x="{x + 104}" y="{yy}" as="targetPoint"/>'
            f'</mxGeometry></mxCell>')
        texto(f"leg_ex{i}_t", txt, x + 120, yy - 9, w - 144, 18, est_txt)

    # status das tabelas
    yy = LEG_Y + 112
    add(f'<mxCell id="leg_impl" value="" style="rounded=0;html=1;fillColor=#FFFFFF;strokeColor={LINHA};'
        f'strokeWidth=1.2;" vertex="1" parent="1"><mxGeometry x="{x + 24}" y="{yy}" width="80" height="22" '
        f'as="geometry"/></mxCell>')
    texto("leg_impl_t", "<b>Implementado</b> no main (migration + API em uso)", x + 120, yy + 2, w - 144, 18, est_txt)
    yy += 32
    add(f'<mxCell id="leg_dev" value="" style="rounded=0;html=1;fillColor=#FFFFFF;strokeColor={LINHA};'
        f'strokeWidth=1.6;dashed=1;dashPattern=6 4;" vertex="1" parent="1"><mxGeometry x="{x + 24}" y="{yy}" '
        f'width="80" height="22" as="geometry"/></mxCell>')
    texto("leg_dev_t", "<b>Em desenvolvimento</b>: migration existe, contrato em validação",
          x + 120, yy + 2, w - 144, 18, est_txt)
    yy += 32
    chip("leg_prop", "PROP", x + 44, yy + 1, PROP_COR, PROP_FUNDO)
    texto("leg_prop_t", "<b>Campo proposto</b> (itálico): sugestão do squad de dados, não existe no código",
          x + 120, yy + 2, w - 144, 18, est_txt)

    marc = [("PK", "chave primária (linha destacada)"), ("FK", "chave estrangeira (sublinhada)"),
            ("UQ", "valor único"), ("NN", "obrigatório (NOT NULL)"), ("CK", "regra CHECK"),
            ("EX", "EXCLUDE (sem sobreposição)"), ("UQ¹", "único só em aberto (parcial)"),
            ("UQ²", "único em conjunto (loan_id, kind)")]
    for i, (m, d) in enumerate(marc):
        xx = x + 24 + (i % 2) * 264
        yy = LEG_Y + 218 + (i // 2) * 25
        cor = "#9A6B00" if m == "PK" else TINTA2
        fundo = PK_FUNDO if m == "PK" else "#FFFFFF"
        chip(f"leg_m{i}", m, xx, yy, cor, fundo, 36)
        texto(f"leg_m{i}_t", escape(d), xx + 44, yy, 214, 19, est_peq)
    texto("leg_tipos", "timestamptz = timestamp with time zone · auth_user.id é integer (padrão do Django)",
          x + 24, LEG_Y + 322, w - 48, 16, f"fontSize=10;fontColor={TINTA3};align=left;verticalAlign=middle;spacing=0;")

    # Cartão 2: regras de integridade
    x, w = 630, 1190
    cartao("leg_regras", x, w)
    texto("leg_regras_tit", f'<b style="font-size:14px;color:{TINTA}">Regras de integridade no banco (já no main)</b>',
          x + 24, LEG_Y + 16, 600, 20, "align=left;verticalAlign=middle;spacing=0;")
    regras = [
        ("UQ¹", "<b>keys_one_active_loan_per_key</b>: UNIQUE (key_id) WHERE returned_at IS NULL — uma chave nunca "
                "tem dois empréstimos ativos"),
        ("CK", "<b>keys_return_not_before_checkout</b>: returned_at vazio ou ≥ checked_out_at"),
        ("CK", "<b>keys_return_time_operator_together</b>: returned_at e return_operator_id preenchidos juntos"),
        ("UQ²", "<b>keys_one_movement_per_loan_kind</b>: no máximo 1 retirada e 1 devolução por empréstimo"),
        ("CK", "<b>keys_movement_kind_valid</b>: kind só aceita 'checkout' ou 'return'"),
        ("TRG", "<b>keys_movement_immutable</b>: trigger bloqueia UPDATE e DELETE em movimentações (histórico preservado)"),
        ("TRG", "<b>keys_key_space_fixed_after_loan</b>: chave com empréstimo não pode mudar de sala"),
        ("EX", "<b>bookings_active_no_overlap</b>: EXCLUDE gist (space_id =, [start_at, end_at) &amp;&amp;) só para "
               "reservas ativas"),
        ("CK", "<b>bookings</b>: start_at &lt; end_at · status 'active'/'cancelled' · cancelled_at só quando cancelada"),
        ("CK", "<b>spaces</b>: code único e não-vazio · kind só 'room' ou 'laboratory'"),
        ("FK", "<b>ON DELETE PROTECT em todas as FKs</b>: nada é apagado em cascata"),
    ]
    for i, (m, txt) in enumerate(regras):
        yy = LEG_Y + 48 + i * 26
        chip(f"leg_r{i}", m, x + 24, yy, TINTA2, "#FFFFFF", 36)
        texto(f"leg_r{i}_t", txt, x + 70, yy, w - 94, 19, est_peq)


if __name__ == "__main__":
    erros = conferir()
    if erros:
        print("\n".join(erros))
        sys.exit(1)
    xml = gerar_drawio()
    ET.fromstring(xml.encode("utf-8"))
    destino = os.path.join(PASTA, "DER-LabTech.drawio")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(xml)
    print("ok:", destino)
