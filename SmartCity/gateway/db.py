"""
db.py — Camada de persistência SQLite do Gateway.
Todas as funções são thread-safe (cada chamada abre/fecha sua própria conexão).
"""

import sqlite3
import time
import math

DB_PATH = "cidade.db"


# ─── Inicialização ────────────────────────────────────────────────────────────

def inicializar():
    """Cria as tabelas se não existirem."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leituras (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT    NOT NULL,
            type      TEXT    NOT NULL,
            valor     REAL    NOT NULL,
            alerta    INTEGER NOT NULL DEFAULT 0,
            timestamp INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leituras_source_ts
        ON leituras (source_id, timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leituras_type_ts
        ON leituras (type, timestamp)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fontes (
            source_id      TEXT    PRIMARY KEY,
            type           TEXT,
            ip             TEXT,
            status         TEXT    DEFAULT 'ativo',
            controllable   INTEGER DEFAULT 0,
            ultima_leitura INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] Banco inicializado em", DB_PATH)


# ─── Escrita ──────────────────────────────────────────────────────────────────

def salvar_leitura(leitura):
    """
    Recebe um objeto Leitura (protobuf) e persiste no banco.
    Também atualiza o timestamp da última leitura da fonte.
    """
    campo = leitura.WhichOneof("valor")
    valor = float(getattr(leitura, campo)) if campo else 0.0

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO leituras (source_id, type, valor, alerta, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (leitura.source_id, leitura.type, valor,
          int(leitura.alerta), leitura.timestamp))

    conn.execute("""
        UPDATE fontes SET ultima_leitura = ? WHERE source_id = ?
    """, (leitura.timestamp, leitura.source_id))

    conn.commit()
    conn.close()


def registrar_fonte(resp):
    """
    Recebe um objeto DiscoveryResponse (protobuf) e persiste/atualiza a fonte.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO fontes (source_id, type, ip, status, controllable)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            ip           = excluded.ip,
            status       = excluded.status,
            controllable = excluded.controllable
    """, (resp.source_id, resp.type, resp.ip,
          resp.status, int(resp.controllable)))
    conn.commit()
    conn.close()


def atualizar_status_fonte(source_id, status):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE fontes SET status = ? WHERE source_id = ?",
        (status, source_id)
    )
    conn.commit()
    conn.close()


# ─── Leitura / Consultas ──────────────────────────────────────────────────────

def listar_fontes():
    """Retorna todas as fontes registradas como lista de dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM fontes ORDER BY source_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def historico(source_id=None, type_=None, segundos=3600, limite=500):
    """
    Retorna leituras recentes como lista de dicts.
    Filtra por source_id OU type, nas últimas `segundos` segundos.
    """
    desde = int(time.time()) - segundos
    conn  = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if source_id:
        rows = conn.execute("""
            SELECT * FROM leituras
            WHERE source_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT ?
        """, (source_id, desde, limite)).fetchall()
    elif type_:
        rows = conn.execute("""
            SELECT * FROM leituras
            WHERE type = ? AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT ?
        """, (type_, desde, limite)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM leituras
            WHERE timestamp >= ?
            ORDER BY timestamp DESC LIMIT ?
        """, (desde, limite)).fetchall()

    conn.close()
    # Inverte para ordem cronológica (mais antigo primeiro → melhor para gráficos)
    return [dict(r) for r in reversed(rows)]


def consulta_media(type_, segundos=3600):
    """Média dos valores de um tipo nas últimas N segundos."""
    desde = int(time.time()) - segundos
    conn  = sqlite3.connect(DB_PATH)
    cur   = conn.execute("""
        SELECT AVG(valor) FROM leituras
        WHERE type = ? AND timestamp >= ?
    """, (type_, desde))
    resultado = cur.fetchone()[0]
    conn.close()
    return round(resultado, 2) if resultado is not None else None


def consulta_desvio_padrao(type_, segundos=86400):
    """Desvio padrão dos valores de um tipo nas últimas N segundos."""
    desde  = int(time.time()) - segundos
    conn   = sqlite3.connect(DB_PATH)
    valores = [r[0] for r in conn.execute("""
        SELECT valor FROM leituras
        WHERE type = ? AND timestamp >= ?
    """, (type_, desde)).fetchall()]
    conn.close()

    if len(valores) < 2:
        return 0.0
    media    = sum(valores) / len(valores)
    variancia = sum((v - media) ** 2 for v in valores) / len(valores)
    return round(math.sqrt(variancia), 2)


def fonte_maior_variacao(segundos=3600):
    """Retorna o source_id com maior desvio padrão nas últimas N segundos."""
    fontes = listar_fontes()
    maior  = None
    maior_dp = -1.0

    for f in fontes:
        desde = int(time.time()) - segundos
        conn  = sqlite3.connect(DB_PATH)
        valores = [r[0] for r in conn.execute("""
            SELECT valor FROM leituras
            WHERE source_id = ? AND timestamp >= ?
        """, (f["source_id"], desde)).fetchall()]
        conn.close()

        if len(valores) < 2:
            continue
        media = sum(valores) / len(valores)
        dp = math.sqrt(sum((v - media) ** 2 for v in valores) / len(valores))
        if dp > maior_dp:
            maior_dp = dp
            maior = f["source_id"]

    return {"source_id": maior, "desvio_padrao": round(maior_dp, 2)}


def total_alertas(segundos=86400):
    """Conta alertas disparados nas últimas N segundos por fonte."""
    desde = int(time.time()) - segundos
    conn  = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows  = conn.execute("""
        SELECT source_id, COUNT(*) as total
        FROM leituras
        WHERE alerta = 1 AND timestamp >= ?
        GROUP BY source_id
        ORDER BY total DESC
    """, (desde,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]