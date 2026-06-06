"""
Gera slides PDF para o Trabalho 1 - SmartCity Distribuido.
Versao melhorada: diagramas de bytes, proto real, fluxo de mensagens.
"""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether, Image
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon, Circle
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Group

from reportlab.lib.pagesizes import landscape
A4_LAND = landscape(A4)
W, H = A4_LAND  # 842 x 595 pts

# ── Larguras de referencia (alinhamento) ─────────────────────────────────────
MARGEM_LAT = 1.5 * cm                 # margem esquerda/direita
UW         = W - 2 * MARGEM_LAT       # largura util ~26.7cm (alinha tudo a esq.)
COL_W      = UW / 2                   # cada coluna no layout de 2 colunas
MONO_W     = COL_W - 0.55 * cm        # bloco de codigo dentro de 1 coluna

# ── Paleta de cores ─────────────────────────────────────────────────────────
AZUL_ESCURO  = colors.HexColor("#0d1b2a")
AZUL_MEDIO   = colors.HexColor("#1b3a5c")
AZUL_CLARO   = colors.HexColor("#2a7ab5")
CIANO        = colors.HexColor("#00b8d4")
VERDE        = colors.HexColor("#00c853")
VERDE_ESCURO = colors.HexColor("#1b5e20")
AMARELO      = colors.HexColor("#ffd600")
LARANJA      = colors.HexColor("#ff6d00")
BRANCO       = colors.white
CINZA_CLARO  = colors.HexColor("#f0f4f8")
CINZA_MEDIO  = colors.HexColor("#cfd8dc")
CINZA_TEXTO  = colors.HexColor("#263238")
VERMELHO     = colors.HexColor("#c62828")
ROXO         = colors.HexColor("#6a1b9a")
ROSA         = colors.HexColor("#ad1457")

# ── Estilos ──────────────────────────────────────────────────────────────────
def es(nome, fonte="Helvetica", tam=11, cor=CINZA_TEXTO, alinha=TA_LEFT,
       bold=False, espaco=4, leading=None):
    fn = "Helvetica-Bold" if bold else fonte
    return ParagraphStyle(nome, fontName=fn, fontSize=tam, textColor=cor,
                          alignment=alinha, spaceAfter=espaco,
                          leading=leading or tam * 1.35)

TITULO_CAPA   = es("tc",  tam=30, cor=BRANCO,     alinha=TA_CENTER, bold=True, espaco=6)
SUBTIT_CAPA   = es("sc",  tam=13, cor=CIANO,      alinha=TA_CENTER, espaco=4)
H_SLIDE       = es("hs",  tam=15, cor=BRANCO,     bold=True, alinha=TA_LEFT, espaco=0)
H2            = es("h2",  tam=12, cor=AZUL_MEDIO, bold=True, espaco=6)
H3            = es("h3",  tam=11, cor=AZUL_CLARO, bold=True, espaco=4)
CORPO         = es("cp",  tam=10, cor=CINZA_TEXTO, espaco=3)
CORPO_SM      = es("sm",  tam=9,  cor=CINZA_TEXTO, espaco=2)
CORPO_B       = es("cpb", tam=10, cor=BRANCO,     espaco=3)
MONO          = es("mo",  fonte="Courier", tam=9,  cor=CINZA_TEXTO, espaco=2)
MONO_B        = es("mob", fonte="Courier", tam=9,  cor=BRANCO,     espaco=2)
MONO_CIANO    = es("mc",  fonte="Courier", tam=9,  cor=CIANO,      espaco=2)
MONO_VERDE    = es("mv",  fonte="Courier", tam=9,  cor=VERDE,      espaco=2)
MONO_AM       = es("mam", fonte="Courier", tam=9,  cor=AMARELO,    espaco=2)
NOTA          = es("nt",  tam=8,  cor=colors.HexColor("#546e7a"), espaco=2)
MEMBRO        = es("mb",  tam=9,  cor=CIANO,      alinha=TA_CENTER, espaco=2)


# ── Canvas callbacks ─────────────────────────────────────────────────────────

def bg_capa(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(AZUL_MEDIO)
    canvas.rect(0, 0, W, H * 0.42, fill=1, stroke=0)
    canvas.setFillColor(CIANO)
    canvas.rect(0, H * 0.42, W, 2, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#0a1628"))
    canvas.rect(0, H - 1.5*cm, W, 1.5*cm, fill=1, stroke=0)
    canvas.restoreState()


def bg_slide(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BRANCO)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, H - 2.1*cm, W, 2.1*cm, fill=1, stroke=0)
    canvas.setFillColor(CIANO)
    canvas.rect(0, H - 2.1*cm - 3, W, 3, fill=1, stroke=0)
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, 0, W, 0.8*cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#546e7a"))
    canvas.drawString(1.5*cm, 0.25*cm, "SmartCity — Trabalho 1 · Distribuicao de Processos e Dados · UFC")
    canvas.setFillColor(CIANO)
    canvas.drawRightString(W - 1.5*cm, 0.25*cm, f"Slide {doc.page}")
    canvas.restoreState()


def on_page(canvas, doc):
    if doc.page == 1:
        bg_capa(canvas, doc)
    else:
        bg_slide(canvas, doc)


# ── Helpers de layout ─────────────────────────────────────────────────────────

def titulo_slide(txt):
    return [Paragraph(txt, H_SLIDE), Spacer(1, 0.85*cm)]


def box_info(titulo, itens, cor_titulo=AZUL_MEDIO, largura=None):
    """Caixa com titulo colorido e lista de itens."""
    dados = [[Paragraph(f"<b>{titulo}</b>",
                        es("bt", tam=10, cor=BRANCO, bold=True, alinha=TA_CENTER))]]
    for item in itens:
        dados.append([Paragraph(item, CORPO_SM)])
    estilo = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cor_titulo),
        ("BACKGROUND", (0, 1), (-1, -1), CINZA_CLARO),
        ("GRID",       (0, 0), (-1, -1), 0.3, CINZA_MEDIO),
        ("PADDING",    (0, 0), (-1, -1), 5),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
    ])
    t = Table(dados, colWidths=[largura] if largura else None)
    t.setStyle(estilo)
    t.hAlign = "LEFT"
    return t


def tabela(cabecalho, linhas, larguras, cor_cab=AZUL_ESCURO, fonte_col0_mono=False):
    dados = [cabecalho] + linhas
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cor_cab),
        ("TEXTCOLOR",  (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CINZA_CLARO, BRANCO]),
        ("GRID",       (0, 0), (-1, -1), 0.4, CINZA_MEDIO),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING",    (0, 0), (-1, -1), 5),
    ])
    if fonte_col0_mono:
        ts.add("FONTNAME", (0, 1), (0, -1), "Courier")
        ts.add("TEXTCOLOR", (0, 1), (0, -1), AZUL_CLARO)
    t = Table(dados, colWidths=larguras)
    t.setStyle(ts)
    t.hAlign = "LEFT"
    return t


def secao(txt):
    return [
        HRFlowable(width="100%", thickness=0.5, color=CIANO, spaceAfter=3),
        Paragraph(txt, H2),
    ]


def bullet(txt, nivel=0, cor=CINZA_TEXTO):
    indent = "&nbsp;" * (nivel * 4)
    return Paragraph(f"{indent}• {txt}", es("bl", tam=10, cor=cor, espaco=3))


def mono_bloco(linhas, largura=None, cor_fundo=colors.HexColor("#1e2a35")):
    """Bloco de codigo escuro com fonte monospacada."""
    if largura is None:
        largura = MONO_W
    texto = "<br/>".join(linhas)
    cel = Paragraph(f'<font face="Courier" size="8" color="white">{texto}</font>',
                    es("cod", tam=8, cor=BRANCO, espaco=0, leading=11))
    t = Table([[cel]], colWidths=[largura])
    t.hAlign = "LEFT"
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cor_fundo),
        ("PADDING",    (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 1 — CAPA
# ─────────────────────────────────────────────────────────────────────────────

def slide_capa():
    e = []
    e.append(Spacer(1, 3.2*cm))
    e.append(Paragraph("SmartCity", TITULO_CAPA))
    e.append(Paragraph("Sistema Distribuido com Sockets e Protocol Buffers", SUBTIT_CAPA))
    e.append(Spacer(1, 0.3*cm))
    e.append(HRFlowable(width="55%", thickness=2, color=CIANO,
                        hAlign="CENTER", spaceAfter=0.4*cm))
    e.append(Paragraph("Distribuicao de Processos e Dados — UFC",
                        es("univ", tam=11, cor=BRANCO, alinha=TA_CENTER)))
    e.append(Paragraph("Prof. Dr. Paulo A. L. Rego",
                        es("prof", tam=9, cor=CINZA_MEDIO, alinha=TA_CENTER, espaco=10)))
    e.append(Spacer(1, 0.8*cm))
    membros = [
        ("Carlos Henrriky Vieira Sousa", "514128"),
        ("Jose Enilson Mesquita da Silva", "497562"),
        ("Maria Eduarda de Sousa Pereira", "510976"),
    ]
    for nome, mat in membros:
        e.append(Paragraph(
            f"{nome} &nbsp;&nbsp;<font color='#ffd600'><b>{mat}</b></font>",
            es("mem", tam=10, cor=BRANCO, alinha=TA_CENTER, espaco=3)))
    e.append(Spacer(1, 1.2*cm))
    e.append(Paragraph("06 de Junho de 2026",
                        es("data", tam=9, cor=colors.HexColor("#78909c"), alinha=TA_CENTER)))
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 2 — VISAO GERAL DA ARQUITETURA
# ─────────────────────────────────────────────────────────────────────────────

def slide_arquitetura():
    e = titulo_slide("Arquitetura do Sistema")

    e.append(Paragraph(
        "Tres processos independentes em tres linguagens diferentes, comunicando via <b>TCP</b>, "
        "<b>UDP unicast</b> e <b>UDP multicast</b>, com todas as mensagens serializadas em "
        "<b>Protocol Buffers</b>.", CORPO))
    e.append(Spacer(1, 0.3*cm))

    dados = [
        ["Componente", "Linguagem / Build", "Responsabilidade"],
        ["Gateway Inteligente", "Python 3.14", "Hub central: coleta, persiste, controla e expoe API"],
        ["Fontes de Dados", "C (GCC 15 + protobuf-c 1.5)", "5 processos: 2 sensores + 3 atuadores urbanos"],
        ["Cliente Analitico", "Java 21 + Maven 3.9", "Menu interativo: consultas, comandos e analytics"],
    ]
    t = tabela(dados[0], dados[1:], [5.2*cm, 6.5*cm, 15*cm])
    e.append(t)
    e.append(Spacer(1, 0.35*cm))

    e.extend(secao("Canais de comunicacao (5 portas)"))
    canais = [
        ["UDP Multicast", "224.1.1.1:5007", "Gateway → Fontes", "DiscoveryRequest (broadcast de descoberta)"],
        ["UDP Unicast",   "0.0.0.0:6002",   "Fontes → Gateway", "DiscoveryResponse (cont.) + Leitura (dados)"],
        ["TCP",          "0.0.0.0:6000",    "Fontes ↔ Gateway", "DiscoveryResponse (ctrl.) + Comando + RespostaComando"],
        ["TCP",          "0.0.0.0:6001",    "Cliente ↔ Gateway","RequisicaoCliente + RespostaGateway"],
        ["HTTP REST",    ":6003",            "Browser ↔ Gateway","JSON — Dashboard Web com Chart.js"],
    ]
    ts = TableStyle([
        ("BACKGROUND", (0,0), (-1,0), AZUL_ESCURO),
        ("TEXTCOLOR",  (0,0), (-1,0), BRANCO),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",   (0,1), (1,-1), "Courier"),
        ("TEXTCOLOR",  (0,1), (0,-1), colors.HexColor("#ff8f00")),
        ("TEXTCOLOR",  (1,1), (1,-1), VERDE),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [CINZA_CLARO, BRANCO]),
        ("GRID",  (0,0), (-1,-1), 0.4, CINZA_MEDIO),
        ("VALIGN",(0,0), (-1,-1), "MIDDLE"),
        ("PADDING",(0,0), (-1,-1), 5),
    ])
    tc = Table([["Protocolo","Porta","Direcao","Mensagens"]] + canais,
               colWidths=[3*cm, 3.7*cm, 4.5*cm, 15.5*cm])
    tc.setStyle(ts)
    tc.hAlign = "LEFT"
    e.append(tc)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 3 — PROTOCOL BUFFERS: DEFINICOES
# ─────────────────────────────────────────────────────────────────────────────

def slide_proto_definicoes():
    e = titulo_slide("Protocol Buffers — Definicoes das Mensagens")

    e.append(Paragraph(
        "Arquivo unico <font face='Courier'>SmartCity/proto/cidade.proto</font> define "
        "<b>7 mensagens</b>. Compilado para Python (<font face='Courier'>cidade_pb2.py</font>), "
        "C (<font face='Courier'>cidade.pb-c.c/.h</font>) e Java "
        "(<font face='Courier'>Cidade.java</font>) com <b>protoc 4.34.1</b>.", CORPO))
    e.append(Spacer(1, 0.25*cm))

    col_esq = [
        Paragraph("<b>DiscoveryRequest</b> <font size='8'>(Gateway→Fontes, multicast)</font>",
                  es("mh", tam=9, cor=AZUL_CLARO, bold=True)),
        mono_bloco([
            "message DiscoveryRequest {",
            "  string gateway_ip   = 1;",
            "  int32  gateway_port = 2; // TCP",
            "}",
        ]),
        Spacer(1, 0.2*cm),
        Paragraph("<b>DiscoveryResponse</b> <font size='8'>(Fonte→Gateway)</font>",
                  es("mh2", tam=9, cor=AZUL_CLARO, bold=True)),
        mono_bloco([
            "message DiscoveryResponse {",
            "  string source_id    = 1;",
            "  string type         = 2;",
            "  string ip           = 3;",
            "  int32  udp_port     = 4;",
            "  bool   controllable = 5;",
            "  string status       = 6;",
            "}",
        ]),
        Spacer(1, 0.2*cm),
        Paragraph("<b>Comando</b> <font size='8'>(Gateway→Fonte, TCP)</font>",
                  es("mh3", tam=9, cor=LARANJA, bold=True)),
        mono_bloco([
            "message Comando {",
            '  string source_id = 1;',
            '  string acao      = 2; // "ativar"',
            '  float  valor     = 3; // set_freq',
            "}",
        ]),
        Spacer(1, 0.2*cm),
        Paragraph("<b>RespostaComando</b> <font size='8'>(Fonte→Gateway)</font>",
                  es("mh4", tam=9, cor=LARANJA, bold=True)),
        mono_bloco([
            "message RespostaComando {",
            "  bool   sucesso  = 1;",
            '  string mensagem = 2;',
            "}",
        ]),
    ]

    col_dir = [
        Paragraph("<b>Leitura</b> <font size='8'>(Fonte→Gateway, UDP)</font>",
                  es("mh5", tam=9, cor=VERDE_ESCURO, bold=True)),
        mono_bloco([
            "message Leitura {",
            "  string source_id  = 1;",
            "  string type       = 2;",
            "  int64  timestamp  = 3;",
            "  oneof valor {       // so um",
            "    float temperatura  = 4;",
            "    float umidade      = 5;",
            "    float co2          = 6;",
            "    float ruido        = 7;",
            "    int32 contagem     = 8;",
            "    float energia      = 9;",
            "  }",
            "  bool alerta = 10;",
            "}",
        ]),
        Spacer(1, 0.2*cm),
        Paragraph("<b>RequisicaoCliente</b> <font size='8'>(Java→Gateway, TCP)</font>",
                  es("mh6", tam=9, cor=ROXO, bold=True)),
        mono_bloco([
            "message RequisicaoCliente {",
            '  string  tipo     = 1; // "listar"',
            "  Comando comando  = 2;",
            '  string  consulta = 3; // "media_temp_1h"',
            "}",
        ]),
        Spacer(1, 0.2*cm),
        Paragraph("<b>RespostaGateway</b> <font size='8'>(Gateway→Java, TCP)</font>",
                  es("mh7", tam=9, cor=ROXO, bold=True)),
        mono_bloco([
            "message RespostaGateway {",
            "  string tipo                       = 1;",
            "  repeated DiscoveryResponse fontes = 2;",
            "  RespostaComando resultado_cmd     = 3;",
            "  string dados_consulta             = 4;",
            "}",
        ]),
    ]

    t2 = Table([[col_esq, col_dir]], colWidths=[COL_W, COL_W])
    t2.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("LINEAFTER",    (0,0), (0,-1), 0.5, CINZA_MEDIO),
        ("LEFTPADDING",  (1,0), (1,-1), 8),
    ]))
    t2.hAlign = "LEFT"
    e.append(t2)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 4 — FRAMING TCP + FLUXO DE DESCOBERTA
# ─────────────────────────────────────────────────────────────────────────────

def slide_framing_fluxo():
    e = titulo_slide("Framing TCP e Fluxo de Descoberta")

    e.extend(secao("Protocolo de framing — identico em Python, C e Java"))
    e.append(Paragraph(
        "Todo envio TCP e prefixado com <b>4 bytes big-endian</b> indicando o tamanho do payload "
        "protobuf. Sem framing, o TCP poderia fundir ou fragmentar mensagens.", CORPO))
    e.append(Spacer(1, 0.2*cm))

    # Diagrama de bytes em tabela
    bytes_hdr = [
        Paragraph("<b>Offset</b>", es("bh", tam=8, cor=BRANCO, alinha=TA_CENTER, bold=True)),
        Paragraph("0", es("b0", tam=9, cor=AMARELO, alinha=TA_CENTER, bold=True)),
        Paragraph("1", es("b1", tam=9, cor=AMARELO, alinha=TA_CENTER, bold=True)),
        Paragraph("2", es("b2", tam=9, cor=AMARELO, alinha=TA_CENTER, bold=True)),
        Paragraph("3", es("b3", tam=9, cor=AMARELO, alinha=TA_CENTER, bold=True)),
        Paragraph("4 … N+3", es("b4", tam=9, cor=CIANO, alinha=TA_CENTER, bold=True)),
    ]
    bytes_val = [
        Paragraph("Conteudo", es("bv", tam=8, cor=BRANCO, alinha=TA_CENTER, bold=True)),
        Paragraph("N >> 24", es("bv0", fonte="Courier", tam=9, cor=AMARELO, alinha=TA_CENTER)),
        Paragraph("N >> 16", es("bv1", fonte="Courier", tam=9, cor=AMARELO, alinha=TA_CENTER)),
        Paragraph("N >> 8",  es("bv2", fonte="Courier", tam=9, cor=AMARELO, alinha=TA_CENTER)),
        Paragraph("N & 0xFF",es("bv3", fonte="Courier", tam=9, cor=AMARELO, alinha=TA_CENTER)),
        Paragraph("Payload protobuf serializado (N bytes)", es("bvp", tam=9, cor=CIANO, alinha=TA_CENTER)),
    ]
    tbytes = Table([bytes_hdr, bytes_val], colWidths=[2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 14.2*cm])
    tbytes.hAlign = "LEFT"
    tbytes.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), AZUL_MEDIO),
        ("BACKGROUND", (1,0), (4,-1), colors.HexColor("#b45309")),
        ("BACKGROUND", (5,0), (5,-1), colors.HexColor("#1565c0")),
        ("TEXTCOLOR",  (0,0), (-1,-1), BRANCO),
        ("GRID",       (0,0), (-1,-1), 0.5, BRANCO),
        ("PADDING",    (0,0), (-1,-1), 5),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    e.append(tbytes)

    e.append(Spacer(1, 0.2*cm))
    impl = [
        ["Linguagem", "Envio (4 bytes + payload)", "Recebimento"],
        ["Python",
         "struct.pack('>I', len(data)) + data",
         "struct.unpack('>I', recv(4))[0]  →  recv(N)"],
        ["C",
         "buf[0..3] = htonl(sz); send(buf,4); send(proto,sz)",
         "recv(4) → ntohl → recv(N)"],
        ["Java",
         "(int >> 24,16,8,0) escrito manual em DataOutputStream",
         "DataInputStream.readInt() → readFully(N)"],
    ]
    ti = tabela(impl[0], impl[1:], [3.2*cm, 13*cm, 10.5*cm], fonte_col0_mono=True)
    e.append(ti)

    e.append(Spacer(1, 0.3*cm))
    e.extend(secao("Sequencia de descoberta"))
    passos = [
        ("<b>1. Boot:</b> Gateway envia <font face='Courier'>DiscoveryRequest{ip, port=6000}</font>"
         " via UDP multicast 224.1.1.1:5007", CINZA_TEXTO),
        ("<b>2. Fontes continuas</b> (sensor_temp, qualidade_ar): respondem com "
         "<font face='Courier'>DiscoveryResponse</font> via UDP unicast → 6002", CINZA_TEXTO),
        ("<b>3. Fontes controlaveis</b> (camera, semaforo, poste): conectam TCP → 6000 "
         "e enviam <font face='Courier'>DiscoveryResponse</font>", CINZA_TEXTO),
        ("<b>4. Gateway</b> persiste cada fonte no SQLite e inicia coleta de "
         "<font face='Courier'>Leitura</font>s periodicas", CINZA_TEXTO),
    ]
    for txt, cor in passos:
        e.append(Paragraph(f"&nbsp;&nbsp;{txt}", es("ps", tam=10, cor=cor, espaco=4)))
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 5 — GATEWAY PYTHON
# ─────────────────────────────────────────────────────────────────────────────

def slide_gateway():
    e = titulo_slide("Gateway Inteligente — Python 3")

    e.append(Paragraph(
        "Processo unico com <b>4 threads</b> concorrentes; estado compartilhado protegido por "
        "<b>threading.Lock</b>. Ponto central de todas as comunicacoes.", CORPO))
    e.append(Spacer(1, 0.25*cm))

    threads = [
        ["Thread", "Porta", "Funcao principal"],
        ["t_udp", ":6002 UDP", "Recebe DiscoveryResponse (fontes continuas) + Leitura; persiste no SQLite"],
        ["t_tcp_fontes", ":6000 TCP", "Aceita conexoes de fontes controlaveis; encaminha Comando e recebe RespostaComando"],
        ["t_tcp_cliente", ":6001 TCP", "Atende 1 cliente Java; processa listar / comando / consulta"],
        ["t_api", ":6003 HTTP", "REST API (http.server); serve dados para o Dashboard Web"],
    ]
    tt = tabela(threads[0], threads[1:], [3.5*cm, 3.7*cm, 19.5*cm], fonte_col0_mono=True)
    e.append(tt)

    e.append(Spacer(1, 0.3*cm))

    col1 = [
        Paragraph("<b>Bibliotecas Python</b>", H3),
        Spacer(1, 0.1*cm),
        tabela(
            ["Biblioteca", "Uso"],
            [
                ["protobuf 5.x", "Serializar/deserializar todas as mensagens"],
                ["sqlite3", "Persistencia (stdlib)"],
                ["socket", "UDP + TCP (stdlib)"],
                ["threading", "4 threads concorrentes (stdlib)"],
                ["struct", "Framing: pack/unpack 4 bytes (stdlib)"],
                ["http.server", "API REST sem framework externo"],
            ],
            [4.3*cm, 8.4*cm],
            fonte_col0_mono=True,
        ),
    ]

    col2 = [
        Paragraph("<b>Trecho de codigo: envio de comando TCP</b>", H3),
        Spacer(1, 0.1*cm),
        mono_bloco([
            "cmd = cidade_pb2.Comando()",
            "cmd.source_id = source_id",
            'cmd.acao     = "ativar"',
            "data = cmd.SerializeToString()",
            "size = struct.pack('&gt;I', len(data))",
            "sock.sendall(size + data)",
            "# leitura da resposta:",
            "raw = recv_all(sock, 4)",
            "n   = struct.unpack('&gt;I', raw)[0]",
            "buf = recv_all(sock, n)",
            "resp = cidade_pb2.RespostaComando()",
            "resp.ParseFromString(buf)",
        ]),
        Spacer(1, 0.15*cm),
        Paragraph(
            "Funcao <font face='Courier'>recv_all(sock, n)</font> garante leitura "
            "completa de N bytes, necessaria pois <font face='Courier'>recv()</font> "
            "pode retornar menos que o solicitado.", NOTA),
    ]

    tc = Table([[col1, col2]], colWidths=[COL_W, COL_W])
    tc.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("LINEAFTER",    (0,0), (0,-1), 0.5, CINZA_MEDIO),
        ("LEFTPADDING",  (1,0), (1,-1), 8),
    ]))
    tc.hAlign = "LEFT"
    e.append(tc)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 6 — FONTES DE DADOS (C)
# ─────────────────────────────────────────────────────────────────────────────

def slide_fontes():
    e = titulo_slide("Fontes de Dados — C (GCC 15 + protobuf-c 1.5)")

    e.append(Paragraph(
        "5 processos independentes compilados via <b>Makefile</b> com "
        "<font face='Courier'>-lprotobuf-c</font>. Cada processo e uma instancia separavel e "
        "executavel em qualquer host da rede.", CORPO))
    e.append(Spacer(1, 0.2*cm))

    fontes = [
        ["Processo", "Tipo", "Dado (campo oneof)", "Comandos aceitos", "Periodicidade"],
        ["sensor_temperatura", "Nao ctrl.", "temperatura (float)", "—", "15 s"],
        ["sensor_qualidade_ar","Nao ctrl.", "co2 (float)",          "—", "10 s"],
        ["camera",            "Controlavel","contagem (int32)",    "ativar, desativar, set_freq", "5 s"],
        ["semaforo",          "Controlavel","contagem (int32)",    "ativar, desativar, set_freq", "3 s"],
        ["poste",             "Controlavel","energia (float)",     "ativar, desativar, set_limiar","8 s"],
    ]
    ts2 = TableStyle([
        ("BACKGROUND", (0,0), (-1,0), AZUL_ESCURO),
        ("TEXTCOLOR",  (0,0), (-1,0), BRANCO),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",   (0,1), (0,-1), "Courier"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("TEXTCOLOR",  (0,1), (0,-1), AZUL_CLARO),
        ("TEXTCOLOR",  (1,1), (1,2),  colors.HexColor("#00695c")),
        ("TEXTCOLOR",  (1,3), (1,5),  LARANJA),
        ("FONTNAME",   (1,1), (1,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [CINZA_CLARO, BRANCO]),
        ("GRID",  (0,0), (-1,-1), 0.4, CINZA_MEDIO),
        ("VALIGN",(0,0), (-1,-1), "MIDDLE"),
        ("PADDING",(0,0), (-1,-1), 5),
    ])
    tf = Table(fontes, colWidths=[5.2*cm, 3.2*cm, 4.3*cm, 9.5*cm, 4.5*cm])
    tf.setStyle(ts2)
    tf.hAlign = "LEFT"
    e.append(tf)

    e.append(Spacer(1, 0.3*cm))

    col1 = [
        Paragraph("<b>Arquitetura interna (fontes controlaveis)</b>", H3),
        bullet("Thread principal: loop UDP — envia <font face='Courier'>Leitura</font> a cada N segundos"),
        bullet("Thread TCP: escuta comandos do Gateway em loop bloqueante"),
        bullet("Variavel global <font face='Courier'>ativo</font> + mutex sincroniza as threads"),
        bullet("Variaveis <font face='Courier'>frequencia</font> e <font face='Courier'>limiar</font> "
               "ajustadas em tempo real pelo comando"),
        Spacer(1, 0.15*cm),
        Paragraph("<b>Bypass WSL2 (arg)</b>", H3),
        Paragraph(
            "Como multicast nao cruza a fronteira WSL2↔Windows, todos os processos "
            "aceitam argumentos <font face='Courier'>&lt;ip&gt; &lt;porta&gt;</font> "
            "para conexao direta, ignorando a fase de descoberta:", CORPO_SM),
        Spacer(1, 0.1*cm),
        mono_bloco([
            "int main(int argc, char *argv[]) {",
            "  if (argc >= 3) {",
            "    // conecta TCP direto",
            "    connect(tcp_fd, &gw, sizeof(gw));",
            "    // registra sem multicast",
            "    enviar_discovery_response();",
            "  } else {",
            "    descobrir_e_registrar(); // multicast",
            "  }",
            "}",
        ]),
    ]

    col2 = [
        Paragraph("<b>Trecho: envio de Leitura em C</b>", H3),
        Spacer(1, 0.1*cm),
        mono_bloco([
            "Cidade__Leitura msg =",
            "  CIDADE__LEITURA__INIT;",
            "msg.source_id = SENSOR_ID;",
            'msg.type      = "temperatura";',
            "msg.timestamp = time(NULL);",
            "msg.temperatura = gerar_temp();",
            "msg.valor_case  =",
            "  CIDADE__LEITURA__VALOR_TEMPERATURA;",
            "msg.alerta = (msg.temperatura > LIMIAR);",
            "",
            "size_t sz = cidade__leitura__",
            "             get_packed_size(&msg);",
            "uint8_t *buf = malloc(sz);",
            "cidade__leitura__pack(&msg, buf);",
            "",
            "// framing: 4 bytes big-endian",
            "uint32_t nl = htonl((uint32_t)sz);",
            "send(tcp_fd, &nl, 4, 0);",
            "send(tcp_fd, buf, sz, 0);",
        ]),
    ]

    tc = Table([[col1, col2]], colWidths=[COL_W, COL_W])
    tc.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("LINEAFTER",    (0,0), (0,-1), 0.5, CINZA_MEDIO),
        ("LEFTPADDING",  (1,0), (1,-1), 8),
    ]))
    tc.hAlign = "LEFT"
    e.append(tc)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 7 — CLIENTE JAVA
# ─────────────────────────────────────────────────────────────────────────────

def slide_cliente():
    e = titulo_slide("Cliente Analitico — Java 21")

    e.append(Paragraph(
        "Processo Java independente, executado com <font face='Courier'>java -jar cliente-1.0.jar</font>. "
        "Conecta ao Gateway via TCP na porta <font face='Courier'>6001</font> usando framing "
        "identico ao Python e C.", CORPO))
    e.append(Spacer(1, 0.2*cm))

    menu = [
        ["Op.", "Descricao", "Mensagem enviada (RequisicaoCliente)"],
        ["1", "Listar fontes conectadas",
         'tipo="listar"'],
        ["2", "Ativar uma fonte",
         'tipo="comando", cmd.acao="ativar"'],
        ["3", "Desativar uma fonte",
         'tipo="comando", cmd.acao="desativar"'],
        ["4", "Alterar frequencia de envio",
         'tipo="comando", cmd.acao="set_frequencia", cmd.valor=N'],
        ["5", "Alterar limiar de alerta",
         'tipo="comando", cmd.acao="set_limiar", cmd.valor=N'],
        ["6", "Media temperatura ultima 1h",
         'tipo="consulta", consulta="media_temp_1h"'],
        ["7", "Desvio padrao CO2 ultimas 24h",
         'tipo="consulta", consulta="desvio_co2_24h"'],
    ]
    tmenu = tabela(menu[0], menu[1:], [1.5*cm, 6.2*cm, 19*cm])
    tmenu.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), AZUL_ESCURO),
        ("TEXTCOLOR",  (0,0), (-1,0), BRANCO),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",   (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",   (2,1), (2,-1), "Courier"),
        ("TEXTCOLOR",  (0,1), (0,-1), CIANO),
        ("TEXTCOLOR",  (2,1), (2,-1), colors.HexColor("#4a235a")),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [CINZA_CLARO, BRANCO]),
        ("GRID",  (0,0), (-1,-1), 0.4, CINZA_MEDIO),
        ("VALIGN",(0,0), (-1,-1), "MIDDLE"),
        ("PADDING",(0,0), (-1,-1), 5),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
    ]))
    e.append(tmenu)

    e.append(Spacer(1, 0.3*cm))

    col1 = [
        Paragraph("<b>Stack Java</b>", H3),
        tabela(
            ["Componente", "Versao / Detalhe"],
            [
                ["Java",              "21 (LTS)"],
                ["Maven",             "3.9 (build + dep)"],
                ["protobuf-java",     "4.34.1 (com.google.protobuf)"],
                ["maven-shade-plugin","uber-JAR com dependencias"],
                ["protoc",            "4.34.1 — gera Cidade.java"],
            ],
            [5*cm, 7.7*cm],
            fonte_col0_mono=True,
        ),
    ]
    col2 = [
        Paragraph("<b>Trecho: envio e leitura de resposta</b>", H3),
        Spacer(1, 0.05*cm),
        mono_bloco([
            "// Envio com framing",
            "RequisicaoCliente req =",
            "  RequisicaoCliente.newBuilder()",
            '    .setTipo("listar")',
            "    .build();",
            "byte[] payload = req.toByteArray();",
            "out.writeInt(payload.length);",
            "out.write(payload);",
            "out.flush();",
            "",
            "// Leitura da resposta",
            "int n = in.readInt();",
            "byte[] buf = new byte[n];",
            "in.readFully(buf);",
            "RespostaGateway resp =",
            "  RespostaGateway.parseFrom(buf);",
        ]),
    ]

    tc = Table([[col1, col2]], colWidths=[COL_W, COL_W])
    tc.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("LINEAFTER",    (0,0), (0,-1), 0.5, CINZA_MEDIO),
        ("LEFTPADDING",  (1,0), (1,-1), 8),
    ]))
    tc.hAlign = "LEFT"
    e.append(tc)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 8 — PERSISTENCIA + API REST
# ─────────────────────────────────────────────────────────────────────────────

def slide_persistencia():
    e = titulo_slide("Persistencia SQLite + API REST")

    col1 = [
        Paragraph("<b>Banco de Dados — cidade.db</b>", H3),
        Spacer(1, 0.1*cm),
        Paragraph("<b>Tabela leituras</b>", es("tl", tam=9, cor=AZUL_CLARO, bold=True)),
        mono_bloco([
            "CREATE TABLE leituras (",
            "  id        INTEGER PRIMARY KEY,",
            "  source_id TEXT,",
            "  type      TEXT,",
            "  valor     REAL,",
            "  alerta    INTEGER,",
            "  timestamp INTEGER",
            ");",
        ]),
        Spacer(1, 0.15*cm),
        Paragraph("<b>Tabela fontes</b>", es("tf2", tam=9, cor=AZUL_CLARO, bold=True)),
        mono_bloco([
            "CREATE TABLE fontes (",
            "  source_id     TEXT PRIMARY KEY,",
            "  type          TEXT,",
            "  ip            TEXT,",
            "  status        TEXT,",
            "  controllable  INTEGER,",
            "  ultima_leitura INTEGER",
            ");",
        ]),
        Spacer(1, 0.15*cm),
        Paragraph("<b>Consultas analiticas implementadas</b>",
                  es("ca", tam=9, cor=AZUL_CLARO, bold=True)),
        bullet("Media por tipo e intervalo de tempo", nivel=0),
        bullet("Desvio padrao por tipo e intervalo", nivel=0),
        bullet("Fonte com maior variacao de valores", nivel=0),
        bullet("Total de alertas por fonte", nivel=0),
    ]

    col2 = [
        Paragraph("<b>API REST — Porta 6003</b>", H3),
        Spacer(1, 0.1*cm),
        tabela(
            ["Metodo", "Rota", "Descricao"],
            [
                ["GET",  "/fontes",                    "Lista todas as fontes"],
                ["GET",  "/historico?type=&segundos=", "Leituras recentes filtradas"],
                ["GET",  "/alertas",                   "Ultimos alertas"],
                ["GET",  "/consultas/media?type=",     "Media por tipo"],
                ["GET",  "/consultas/desvio?type=",    "Desvio padrao"],
                ["GET",  "/consultas/maior_variacao",  "Fonte mais variavel"],
                ["GET",  "/consultas/alertas",         "Total alertas/fonte"],
                ["POST", "/comando",                   "Envia comando a fonte"],
            ],
            [1.9*cm, 5.4*cm, 5.3*cm],
        ),
        Spacer(1, 0.2*cm),
        Paragraph("<b>Dashboard Web</b>", H3),
        bullet("Arquivo unico <font face='Courier'>dashboard.html</font> (sem build)"),
        bullet("Chart.js 4.4 (CDN) — graficos de series temporais"),
        bullet("Polling a cada 5 s na API REST"),
        bullet("Envia comandos via <font face='Courier'>POST /comando</font>"),
        bullet("CORS: <font face='Courier'>Access-Control-Allow-Origin: *</font>"),
    ]

    tc = Table([[col1, col2]], colWidths=[COL_W, COL_W])
    tc.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("LINEAFTER",    (0,0), (0,-1), 0.5, CINZA_MEDIO),
        ("LEFTPADDING",  (1,0), (1,-1), 8),
    ]))
    tc.hAlign = "LEFT"
    e.append(tc)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 9 — TECNOLOGIAS + PONTUACAO EXTRA
# ─────────────────────────────────────────────────────────────────────────────

def slide_tecnologias():
    e = titulo_slide("Tecnologias, Frameworks e Bibliotecas")

    e.extend(secao("Stack completo de tecnologias"))
    tec = [
        ["Camada",         "Tecnologia",          "Versao",   "Papel no sistema"],
        ["Serializacao",   "Protocol Buffers",     "4.34.1",   "Todas as msgs entre todos os processos"],
        ["Gateway",        "Python",               "3.14",     "Orchestrador central; threading + sqlite3"],
        ["Fontes",         "C / GCC",              "15.2",     "Processos nativos de alta performance"],
        ["Fontes lib",     "protobuf-c",            "1.5.1",    "Serializacao protobuf em C puro"],
        ["Cliente",        "Java",                 "21 LTS",   "JVM; DataInputStream/OutputStream"],
        ["Build Java",     "Maven + shade-plugin", "3.9",      "Uber-JAR com todas as deps embutidas"],
        ["Persistencia",   "SQLite",               "stdlib",   "Banco embutido, zero configuracao"],
        ["API",            "http.server",          "stdlib",   "Servidor HTTP sem framework externo"],
        ["Dashboard",      "Chart.js",             "4.4 (CDN)","Graficos no browser; polling REST"],
    ]
    tt = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0,0), (-1,0), BRANCO),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME",      (0,1), (1,-1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (0,1), (0,-1), CIANO),
        ("TEXTCOLOR",     (1,1), (1,-1), AZUL_CLARO),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [CINZA_CLARO, BRANCO]),
        ("GRID",          (0,0), (-1,-1), 0.4, CINZA_MEDIO),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("PADDING",       (0,0), (-1,-1), 5),
    ])
    t_tec = Table(tec, colWidths=[3.5*cm, 5*cm, 3*cm, 15.2*cm])
    t_tec.setStyle(tt)
    t_tec.hAlign = "LEFT"
    e.append(t_tec)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 10 — REQUISITOS ATENDIDOS
# ─────────────────────────────────────────────────────────────────────────────

def slide_requisitos():
    e = titulo_slide("Requisitos Atendidos — Conclusao")

    req = [
        ["Requisito", "Evidencia", "OK"],
        ["Protobuf em TODOS os trocas de mensagens",
         "cidade.proto compilado para Python, C e Java; usado em todos os envios", "✓"],
        ["TCP para controle (cliente + fontes controlaveis)",
         "Porta 6001 (cliente) e 6000 (fontes); framing 4 bytes em todas as linguagens", "✓"],
        ["UDP para dados continuos (sensores)",
         "sensor_temp e qualidade_ar enviam Leitura via UDP unicast porta 6002", "✓"],
        ["UDP Multicast para descoberta",
         "Gateway transmite DiscoveryRequest em 224.1.1.1:5007 ao iniciar", "✓"],
        ["2 fontes nao-controlaveis",
         "sensor_temperatura e sensor_qualidade_ar — apenas enviam leituras", "✓"],
        ["3 fontes controlaveis",
         "camera, semaforo, poste — aceitam comandos ativar/desativar/set_freq/set_limiar", "✓"],
        ["Cliente lista fontes",
         "Opcao 1 do menu — RequisicaoCliente{tipo=listar}", "✓"],
        ["Cliente envia comandos",
         "Opcoes 2,3,4,5 — Comando embutido em RequisicaoCliente", "✓"],
        ["Cliente realiza consultas agregadas",
         "Opcoes 6,7 — media_temp_1h e desvio_co2_24h via SQLite", "✓"],
        ["[Extra] Persistencia SQLite",
         "db.py — tabelas leituras e fontes; funcoes agregadas implementadas", "✓"],
        ["[Extra] Multiplas linguagens",
         "Python + C + Java — tres compiladores, um protocolo comum", "✓"],
        ["[Extra] Dashboard grafico",
         "dashboard.html + Chart.js — graficos em tempo real + comandos via browser", "✓"],
    ]

    tr = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0,0), (-1,0), BRANCO),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",       (0,0), (-1,-1), 9),
        ("TEXTCOLOR",     (2,1), (2,-1), VERDE),
        ("FONTNAME",      (2,1), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (2,1), (2,-1), 12),
        ("ROWBACKGROUNDS",(0,1), (-1,9),  [CINZA_CLARO, BRANCO]),
        ("ROWBACKGROUNDS",(0,10),(-1,-1), [colors.HexColor("#e8f5e9"), colors.HexColor("#f1f8e9"), colors.HexColor("#e8f5e9")]),
        ("GRID",          (0,0), (-1,-1), 0.4, CINZA_MEDIO),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("PADDING",       (0,0), (-1,-1), 5),
        ("ALIGN",         (2,0), (2,-1), "CENTER"),
    ])
    t_req = Table(req, colWidths=[8*cm, 16.2*cm, 2.5*cm])
    t_req.setStyle(tr)
    t_req.hAlign = "LEFT"
    e.append(t_req)

    e.append(Spacer(1, 0.4*cm))
    e.append(HRFlowable(width="100%", thickness=1.5, color=CIANO))
    e.append(Spacer(1, 0.2*cm))
    e.append(Paragraph(
        "Sistema SmartCity completamente funcional — Gateway Python + 5 fontes C + "
        "Cliente Java comunicando via Protocol Buffers sobre TCP e UDP.",
        es("concl", tam=10, cor=AZUL_MEDIO, alinha=TA_CENTER, bold=True)))
    return e


# ─────────────────────────────────────────────────────────────────────────────
# GERACAO DO PDF
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT = r"C:\Users\Usuario\Desktop\projeto\Apresentacao_SmartCity.pdf"
MARGEM = 1.5 * cm

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4_LAND,
    leftMargin=MARGEM,
    rightMargin=MARGEM,
    topMargin=0.8*cm,      # capa: pouca margem (bg_capa preenche)
    bottomMargin=1.2*cm,
    title="SmartCity — Trabalho 1 Sockets",
    author="Carlos Henrriky · Jose Enilson · Maria Eduarda",
    subject="Distribuicao de Processos e Dados — UFC",
)

MARGEM_TOPO_SLIDES = 2.5*cm   # espaco para barra azul no topo

slides = [
    (slide_capa,          0.8*cm),
    (slide_arquitetura,   MARGEM_TOPO_SLIDES),
    (slide_proto_definicoes, MARGEM_TOPO_SLIDES),
    (slide_framing_fluxo, MARGEM_TOPO_SLIDES),
    (slide_gateway,       MARGEM_TOPO_SLIDES),
    (slide_fontes,        MARGEM_TOPO_SLIDES),
    (slide_cliente,       MARGEM_TOPO_SLIDES),
    (slide_persistencia,  MARGEM_TOPO_SLIDES),
    (slide_tecnologias,   MARGEM_TOPO_SLIDES),
]

story = []
for i, (fn, _) in enumerate(slides):
    story.extend(fn())
    if i < len(slides) - 1:
        story.append(PageBreak())

doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print(f"PDF gerado: {OUTPUT}  ({len(slides)} slides)")
