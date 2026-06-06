"""
gateway.py — Gateway Inteligente.
Threads:
  1. Multicast UDP  → envia DiscoveryRequest periodicamente
  2. UDP 6002       → recebe DiscoveryResponse (fontes contínuas) + Leitura
  3. TCP 6000       → registra fontes controláveis + encaminha comandos
  4. TCP 6001       → atende o Cliente Analítico Java
  5. HTTP 6003      → API REST para o dashboard web
"""

import socket
import struct
import threading
import time
import json
import queue
import sys

# Garante UTF-8 na saída (evita UnicodeEncodeError com emojis/acentos em
# consoles cp1252 do Windows, que antes descartava leituras de alerta).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cidade_pb2
import db
import api

# ─── Configurações ────────────────────────────────────────────────────────────
MULTICAST_GROUP    = "224.1.1.1"
MULTICAST_PORT     = 5007
GATEWAY_TCP_FONTES = 6000
CLIENT_TCP_PORT    = 6001
GATEWAY_UDP_PORT   = 6002
API_HTTP_PORT      = 6003

# ─── Estado compartilhado ─────────────────────────────────────────────────────
fontes = {}          # source_id → {"info": DiscoveryResponse, "conn": socket | None}
lock   = threading.Lock()


# ─── Helpers de framing TCP (prefixo 4 bytes big-endian) ─────────────────────

def recv_msg(conn):
    """Lê uma mensagem prefixada com 4 bytes de tamanho. Retorna bytes ou None."""
    try:
        header = conn.recv(4, socket.MSG_WAITALL)
        if not header or len(header) < 4:
            return None
        tamanho = struct.unpack(">I", header)[0]
        dados = b""
        while len(dados) < tamanho:
            chunk = conn.recv(tamanho - len(dados))
            if not chunk:
                return None
            dados += chunk
        return dados
    except Exception:
        return None


def send_msg(conn, dados: bytes):
    """Envia bytes prefixados com 4 bytes de tamanho."""
    msg = struct.pack(">I", len(dados)) + dados
    conn.sendall(msg)


# ─── Thread 1: Multicast Discovery ───────────────────────────────────────────

def enviar_discovery():
    """Envia DiscoveryRequest via multicast UDP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    req = cidade_pb2.DiscoveryRequest()
    req.gateway_port = GATEWAY_TCP_FONTES

    dados = req.SerializeToString()
    msg   = struct.pack(">I", len(dados)) + dados

    sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
    sock.close()
    print("[Discovery] DiscoveryRequest multicast enviado.")


# ─── Thread 2: UDP — DiscoveryResponse + Leituras ────────────────────────────

def thread_udp():
    """
    Porta única 6002 recebe dois tipos de mensagem:
      • DiscoveryResponse → registra fonte contínua
      • Leitura           → salva no banco
    Distinção feita via WhichOneof("valor"):
      - presente  → Leitura
      - ausente   → DiscoveryResponse
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", GATEWAY_UDP_PORT))
    print(f"[UDP] Escutando na porta {GATEWAY_UDP_PORT}")

    while True:
        try:
            dados, addr = sock.recvfrom(65535)
            if len(dados) < 4:
                continue

            tamanho = struct.unpack(">I", dados[:4])[0]
            payload = dados[4:4 + tamanho]

            # Tenta como Leitura primeiro (tem campo 'valor' oneof)
            leitura = cidade_pb2.Leitura()
            leitura.ParseFromString(payload)

            if leitura.WhichOneof("valor") is not None:
                _processar_leitura(leitura)
            else:
                # Sem campo 'valor' → deve ser DiscoveryResponse
                resp = cidade_pb2.DiscoveryResponse()
                resp.ParseFromString(payload)
                if resp.source_id:
                    _registrar_fonte_continua(resp, addr)
                else:
                    print(f"[UDP] Mensagem não reconhecida de {addr}")

        except Exception as e:
            print(f"[UDP] Erro: {e}")


def _processar_leitura(leitura):
    campo = leitura.WhichOneof("valor")
    valor = getattr(leitura, campo) if campo else 0.0
    alerta = " ⚠️  ALERTA" if leitura.alerta else ""
    print(f"[UDP] {leitura.source_id} | {leitura.type} | {campo}={valor:.2f}{alerta}")
    db.salvar_leitura(leitura)


def _registrar_fonte_continua(resp, addr):
    """Registra fontes contínuas (controllable=0) que chegam via UDP."""
    with lock:
        fontes[resp.source_id] = {"info": resp, "conn": None}
    db.registrar_fonte(resp)
    print(f"[UDP] Fonte registrada: {resp.source_id} ({resp.type}) de {addr[0]}")


# ─── Thread 3: TCP — registro e comandos para fontes controláveis ─────────────

def thread_tcp_fontes():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", GATEWAY_TCP_FONTES))
    srv.listen(20)
    print(f"[TCP-Fontes] Escutando na porta {GATEWAY_TCP_FONTES}")

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=_handle_fonte, args=(conn, addr), daemon=True)
        t.start()


def _handle_fonte(conn, addr):
    """
    Recebe DiscoveryResponse via TCP.
    Apenas fontes controláveis (controllable=1) chegam aqui.
    Mantém conexão aberta para envio de comandos futuros.
    """
    dados = recv_msg(conn)
    if not dados:
        conn.close()
        return

    resp = cidade_pb2.DiscoveryResponse()
    resp.ParseFromString(dados)

    if not resp.controllable:
        print(f"[TCP-Fontes] Rejeitado {resp.source_id}: não é controlável.")
        conn.close()
        return

    resp_q   = queue.Queue()
    cmd_lock = threading.Lock()
    with lock:
        fontes[resp.source_id] = {
            "info": resp, "conn": conn,
            "resp_q": resp_q, "cmd_lock": cmd_lock,
        }

    db.registrar_fonte(resp)
    print(f"[TCP-Fontes] Fonte controlável registrada: {resp.source_id} ({resp.type}) de {addr[0]}")

    # Thread leitora ÚNICA deste socket: recebe os RespostaComando e os entrega
    # via fila. Assim o envio de comandos não disputa leitura no mesmo socket
    # (a leitura em recv_msg também detecta a desconexão, retornando None).
    while True:
        dados = recv_msg(conn)
        if dados is None:
            break
        resp_q.put(dados)

    with lock:
        if resp.source_id in fontes:
            fontes[resp.source_id]["conn"] = None

    conn.close()
    print(f"[TCP-Fontes] Fonte desconectada: {resp.source_id}")


# ─── Thread 4: TCP — atende o Cliente Analítico Java ─────────────────────────

def thread_tcp_cliente():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", CLIENT_TCP_PORT))
    srv.listen(5)
    print(f"[TCP-Cliente] Escutando na porta {CLIENT_TCP_PORT}")

    while True:
        conn, addr = srv.accept()
        print(f"[TCP-Cliente] Cliente conectado: {addr}")
        t = threading.Thread(target=_handle_cliente, args=(conn,), daemon=True)
        t.start()


def _handle_cliente(conn):
    while True:
        dados = recv_msg(conn)
        if not dados:
            break

        req = cidade_pb2.RequisicaoCliente()
        req.ParseFromString(dados)

        if req.tipo == "listar":
            resp = _resp_listar()
        elif req.tipo == "comando":
            resp = _resp_comando(req.comando)
        elif req.tipo == "consulta":
            resp = _resp_consulta(req.consulta)
        else:
            resp = cidade_pb2.RespostaGateway()
            resp.tipo = "erro"
            resp.dados_consulta = json.dumps({"erro": "Tipo de requisição desconhecido"})

        send_msg(conn, resp.SerializeToString())

    conn.close()


def _resp_listar():
    resp = cidade_pb2.RespostaGateway()
    resp.tipo = "fontes"
    with lock:
        for f in fontes.values():
            entrada = resp.fontes.add()
            entrada.CopyFrom(f["info"])
    return resp


# ─── Envio de comando TCP — reutilizado por _resp_comando e pela API HTTP ─────

def _enviar_comando(cmd, conn_fonte):
    """
    Envia um Comando via TCP para uma fonte controlável e aguarda o
    RespostaComando. A resposta é entregue pela thread leitora do socket
    (_handle_fonte) através de uma fila — evitando dois leitores no mesmo
    socket. Em caso de erro/timeout retorna RespostaComando com sucesso=False.
    """
    rc = cidade_pb2.RespostaComando()

    with lock:
        fonte = fontes.get(cmd.source_id)

    if not fonte or not fonte.get("conn") or "resp_q" not in fonte:
        rc.sucesso  = False
        rc.mensagem = f"Fonte '{cmd.source_id}' não é controlável ou está desconectada"
        return rc

    cmd_lock = fonte["cmd_lock"]
    resp_q   = fonte["resp_q"]

    with cmd_lock:  # um comando em voo por fonte
        # descarta eventuais respostas pendentes antigas
        try:
            while True:
                resp_q.get_nowait()
        except queue.Empty:
            pass

        try:
            send_msg(conn_fonte, cmd.SerializeToString())
            resposta_bytes = resp_q.get(timeout=5.0)
            rc.ParseFromString(resposta_bytes)

            # Atualiza status no banco para ações de ciclo de vida
            if cmd.acao in ("ativar", "desativar"):
                db.atualizar_status_fonte(cmd.source_id, cmd.acao + "do")

        except queue.Empty:
            rc.sucesso  = False
            rc.mensagem = "Sem resposta da fonte (timeout)"
        except Exception as e:
            rc.sucesso  = False
            rc.mensagem = f"Erro ao enviar comando: {e}"

    return rc


def _resp_comando(cmd):
    """Wrapper para o cliente Java: resolve conn_fonte e delega a _enviar_comando."""
    resp = cidade_pb2.RespostaGateway()
    resp.tipo = "comando_ok"

    with lock:
        fonte = fontes.get(cmd.source_id)

    if not fonte:
        resp.resultado_cmd.sucesso  = False
        resp.resultado_cmd.mensagem = f"Fonte '{cmd.source_id}' não encontrada"
        return resp

    conn_fonte = fonte.get("conn")
    if not conn_fonte:
        resp.resultado_cmd.sucesso  = False
        resp.resultado_cmd.mensagem = f"Fonte '{cmd.source_id}' não é controlável ou está desconectada"
        return resp

    rc = _enviar_comando(cmd, conn_fonte)
    resp.resultado_cmd.CopyFrom(rc)
    return resp


def _resp_consulta(consulta):
    resp = cidade_pb2.RespostaGateway()
    resp.tipo = "consulta"

    try:
        if consulta == "media_temp_1h":
            v = db.consulta_media("temperatura", 3600)
            resp.dados_consulta = json.dumps({"media_temperatura_1h": v})
        elif consulta == "desvio_co2_24h":
            v = db.consulta_desvio_padrao("qualidade_ar", 86400)
            resp.dados_consulta = json.dumps({"desvio_co2_24h": v})
        elif consulta == "maior_variacao":
            v = db.fonte_maior_variacao(3600)
            resp.dados_consulta = json.dumps(v)
        elif consulta == "alertas_24h":
            v = db.total_alertas(86400)
            resp.dados_consulta = json.dumps(v)
        else:
            resp.dados_consulta = json.dumps({"erro": f"Consulta '{consulta}' desconhecida"})

    except Exception as e:
        resp.dados_consulta = json.dumps({"erro": str(e)})

    return resp


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.inicializar()

    # Injeta estado e função de comando na API HTTP antes de iniciar as threads
    api.set_fontes_ref(fontes, lock)
    api.set_comando_fn(_enviar_comando)

    threads = [
        threading.Thread(target=thread_udp,         daemon=True, name="UDP"),
        threading.Thread(target=thread_tcp_fontes,  daemon=True, name="TCP-Fontes"),
        threading.Thread(target=thread_tcp_cliente, daemon=True, name="TCP-Cliente"),
        threading.Thread(target=api.iniciar,        daemon=True, name="API-HTTP",
                         kwargs={"port": API_HTTP_PORT}),
    ]

    for t in threads:
        t.start()
        print(f"[Main] Thread '{t.name}' iniciada.")

    # Aguarda threads subirem antes do primeiro discovery
    time.sleep(1)
    enviar_discovery()

    # Reenvia discovery a cada 30s para capturar fontes que subirem depois
    while True:
        time.sleep(30)
        print("[Main] Reenviando discovery...")
        enviar_discovery()