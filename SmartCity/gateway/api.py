"""
api.py — API REST HTTP do Gateway Inteligente.
Porta padrão: 6003

Rotas:
  GET  /fontes                          → lista todas as fontes registradas
  GET  /historico                       → leituras históricas (filtros via query string)
  GET  /alertas                         → leituras com alerta=True
  GET  /consultas/media                 → média de um tipo num intervalo
  GET  /consultas/desvio                → desvio padrão de um tipo num intervalo
  GET  /consultas/maior_variacao        → fonte com maior variação num intervalo
  GET  /consultas/alertas               → total de alertas por fonte num intervalo
  POST /comando                         → envia comando a uma fonte controlável
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import cidade_pb2
import db

# ─── Estado compartilhado (injetado pelo gateway.py) ─────────────────────────
_fontes: dict = {}
_lock: threading.Lock = threading.Lock()

# Referência ao dicionário de fontes do gateway (injetada via set_fontes_ref)
_enviar_comando_fn = None  # callable(cmd: Comando) → RespostaComando


def set_fontes_ref(fontes: dict, lock: threading.Lock):
    global _fontes, _lock
    _fontes = fontes
    _lock   = lock


def set_comando_fn(fn):
    """Injeta a função de envio de comandos do gateway."""
    global _enviar_comando_fn
    _enviar_comando_fn = fn


# ─── Handler HTTP ─────────────────────────────────────────────────────────────

class GatewayAPIHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Suprime logs de acesso padrão — o gateway já loga o suficiente
        pass

    # ── CORS — permite que o dashboard (qualquer origem) acesse a API ──────
    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs     = parse_qs(parsed.query)
        path   = parsed.path.rstrip("/")

        # ── GET /fontes ───────────────────────────────────────────────────
        if path == "/fontes":
            with _lock:
                lista = []
                for sid, f in _fontes.items():
                    info = f["info"]
                    lista.append({
                        "source_id":   info.source_id,
                        "type":        info.type,
                        "ip":          info.ip,
                        "udp_port":    info.udp_port,
                        "controllable": bool(info.controllable),
                        "status":      info.status,
                        "conectado":   f["conn"] is not None,
                    })
            self._responder(lista)

        # ── GET /historico ────────────────────────────────────────────────
        # Parâmetros opcionais: type, source_id, segundos (default 3600), limite (default 100)
        elif path == "/historico":
            tipo      = qs.get("type",      [None])[0]
            source_id = qs.get("source_id", [None])[0]
            segundos  = int(qs.get("segundos", ["3600"])[0])
            limite    = int(qs.get("limite",   ["100"])[0])
            # assinatura real: historico(source_id, type_, segundos, limite)
            dados = db.historico(source_id=source_id, type_=tipo,
                                 segundos=segundos, limite=limite)
            self._responder(dados)

        # ── GET /alertas ──────────────────────────────────────────────────
        # Filtra alerta=1 no Python (db.historico não tem apenas_alertas)
        elif path == "/alertas":
            tipo      = qs.get("type",      [None])[0]
            source_id = qs.get("source_id", [None])[0]
            segundos  = int(qs.get("segundos", ["3600"])[0])
            limite    = int(qs.get("limite",   ["50"])[0])
            todos = db.historico(source_id=source_id, type_=tipo,
                                 segundos=segundos, limite=500)
            dados = [d for d in todos if d.get("alerta")][:limite]
            self._responder(dados)

        # ── GET /consultas/media ──────────────────────────────────────────
        # Parâmetros: type (obrigatório), segundos (default 3600)
        elif path == "/consultas/media":
            tipo     = qs.get("type",     [None])[0]
            segundos = int(qs.get("segundos", ["3600"])[0])
            if not tipo:
                return self._erro(400, "Parâmetro 'type' obrigatório.")
            v = db.consulta_media(tipo, segundos)
            self._responder({"type": tipo, "segundos": segundos, "media": round(v, 2) if v is not None else None})

        # ── GET /consultas/desvio ─────────────────────────────────────────
        # Parâmetros: type (obrigatório), segundos (default 86400)
        elif path == "/consultas/desvio":
            tipo     = qs.get("type",     [None])[0]
            segundos = int(qs.get("segundos", ["86400"])[0])
            if not tipo:
                return self._erro(400, "Parâmetro 'type' obrigatório.")
            v = db.consulta_desvio_padrao(tipo, segundos)
            self._responder({"type": tipo, "segundos": segundos, "desvio_padrao": round(v, 2) if v is not None else None})

        # ── GET /consultas/maior_variacao ─────────────────────────────────
        # Parâmetros: segundos (default 3600)
        elif path == "/consultas/maior_variacao":
            segundos = int(qs.get("segundos", ["3600"])[0])
            v = db.fonte_maior_variacao(segundos)
            self._responder(v)

        # ── GET /consultas/alertas ────────────────────────────────────────
        # Parâmetros: segundos (default 86400)
        elif path == "/consultas/alertas":
            segundos = int(qs.get("segundos", ["86400"])[0])
            v = db.total_alertas(segundos)
            self._responder(v)

        else:
            self._erro(404, f"Rota '{path}' não encontrada.")

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        # ── POST /comando ─────────────────────────────────────────────────
        if path == "/comando":
            length  = int(self.headers.get("Content-Length", 0))
            body    = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return self._erro(400, "JSON inválido.")

            source_id = payload.get("source_id", "")
            acao      = payload.get("acao", "")
            valor     = float(payload.get("valor", 0))

            if not source_id or not acao:
                return self._erro(400, "Campos 'source_id' e 'acao' são obrigatórios.")

            with _lock:
                fonte = _fontes.get(source_id)

            if not fonte:
                return self._responder({"sucesso": False, "mensagem": f"Fonte '{source_id}' não encontrada."})

            conn = fonte.get("conn")
            if not conn:
                return self._responder({"sucesso": False, "mensagem": f"Fonte '{source_id}' não é controlável ou está desconectada."})

            if _enviar_comando_fn is None:
                return self._erro(500, "Função de comando não registrada.")

            cmd = cidade_pb2.Comando()
            cmd.source_id = source_id
            cmd.acao      = acao
            cmd.valor     = valor

            resultado = _enviar_comando_fn(cmd, conn)
            self._responder({
                "sucesso":  resultado.sucesso,
                "mensagem": resultado.mensagem,
            })

        else:
            self._erro(404, f"Rota POST '{path}' não encontrada.")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _responder(self, dados, status=200):
        body = json.dumps(dados, ensure_ascii=False).encode()
        self._set_headers(status)
        self.wfile.write(body)

    def _erro(self, status, mensagem):
        self._responder({"erro": mensagem}, status=status)


# ─── Inicialização ────────────────────────────────────────────────────────────

def iniciar(port: int = 6003):
    srv = HTTPServer(("", port), GatewayAPIHandler)
    print(f"[API] HTTP REST escutando na porta {port}")
    srv.serve_forever()