#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# demo_fontes.sh — Inicia todas as fontes de dados para a demonstração
#
# Uso:
#   ./demo_fontes.sh [<ip_gateway>]
#
#   <ip_gateway>  IP onde o Gateway Python está rodando.
#                 Default: 127.0.0.1  (tudo no mesmo WSL/Linux)
#                 WSL→Windows: use o IP retornado por  cat /etc/resolv.conf
#
# O script:
#   1. Compila os binários C (make)
#   2. Sobe os 2 sensores contínuos (UDP) em background
#   3. Sobe os 3 atuadores controláveis (TCP) em background
#   4. Exibe os PIDs e como simular uma falha
#   5. Encerra tudo ao pressionar Ctrl+C
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GW_IP="${1:-127.0.0.1}"
GW_TCP=6000
GW_UDP=6002
DIR="$(cd "$(dirname "$0")" && pwd)"

sep() { printf '\n%s\n' "────────────────────────────────────────────"; }

cleanup() {
    sep
    echo "Encerrando todas as fontes..."
    # mata somente os filhos diretos deste script
    kill "${PIDS[@]}" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "OK — todas as fontes encerradas."
}
trap cleanup INT TERM EXIT

# ── 1. Compilação ─────────────────────────────────────────────────────────────
sep
echo "SmartCity — Demo: Fontes de Dados"
echo "Gateway:  ${GW_IP}  (TCP=${GW_TCP}  UDP=${GW_UDP})"
sep
echo ">>> Compilando fontes C..."
cd "$DIR"
make -s 2>&1 && echo "Compilação OK." || { echo "ERRO na compilação. Abortando."; exit 1; }

# ── 2. Sensores contínuos (UDP) ───────────────────────────────────────────────
sep
echo ">>> Iniciando sensores contínuos (UDP)..."

./sensor_temperatura  "$GW_IP" "$GW_UDP" &
PID_TEMP=$!
echo "    [1] sensor_temperatura   PID=$PID_TEMP"

./sensor_qualidade_ar "$GW_IP" "$GW_UDP" &
PID_AR=$!
echo "    [2] sensor_qualidade_ar  PID=$PID_AR"

PIDS=($PID_TEMP $PID_AR)

sleep 1

# ── 3. Atuadores controláveis (TCP) ──────────────────────────────────────────
sep
echo ">>> Iniciando atuadores controláveis (TCP)..."

./camera   "$GW_IP" "$GW_TCP" &
PID_CAM=$!
echo "    [3] camera   PID=$PID_CAM"

./semaforo "$GW_IP" "$GW_TCP" &
PID_SEM=$!
echo "    [4] semaforo PID=$PID_SEM"

./poste    "$GW_IP" "$GW_TCP" &
PID_POST=$!
echo "    [5] poste    PID=$PID_POST"

PIDS+=($PID_CAM $PID_SEM $PID_POST)

# ── 4. Instruções de falha ────────────────────────────────────────────────────
sep
echo "Todas as 5 fontes em execução:"
echo ""
echo "  Para simular FALHA de sensor UDP (desaparece silenciosamente):"
echo "    kill $PID_TEMP      ← derruba sensor_temperatura"
echo ""
echo "  Para simular FALHA de atuador TCP (Gateway detecta imediatamente):"
echo "    kill $PID_CAM       ← derruba camera_01"
echo ""
echo "  Pressione Ctrl+C para encerrar tudo."
sep

# Aguarda até Ctrl+C
wait
