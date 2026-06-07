# ✅ Conformidade com a Especificação — Trabalho 1: Sockets

Documento de rastreabilidade entre cada requisito da especificação
(*Distribuição de Processos e Dados — Prof. Dr. Paulo A. L. Rego*) e a
implementação correspondente neste repositório.

Legenda: ✅ atendido · ➕ pontuação extra atendida

---

## 1. Comunicação e Serialização

| # | Requisito | Status | Onde está implementado |
|---|---|---|---|
| 1.a.i | Protobuf em **todas** as mensagens Gateway ↔ Fontes | ✅ | `proto/cidade.proto` (7 mensagens); serialização em `gateway.py`, `*.c`, `Cidade.java` |
| 1.a.ii | Protobuf em **todas** as mensagens Gateway ↔ Cliente | ✅ | `RequisicaoCliente` / `RespostaGateway` em `cidade.proto`; `ClienteAnalitico.java` |
| 1.b.i | **TCP** para controle Cliente ↔ Gateway | ✅ | Gateway porta `6001` (`thread_tcp_cliente`); Cliente conecta via `Socket` |
| 1.b.ii | **UDP** para o fluxo de dados Fontes → Gateway | ✅ | Gateway porta `6002` (`thread_udp`); sensores enviam `Leitura` via `sendto` |
| 1.b.iii | **UDP Multicast** para descoberta inicial | ✅ | Grupo `224.1.1.1:5007`; `enviar_discovery()` + `descobrir_gateway()` nas fontes |

**Framing:** todo envio TCP/UDP é prefixado por 4 bytes big-endian com o tamanho do
payload protobuf — idêntico em Python (`struct.pack(">I", ...)`), C (shifts manuais)
e Java (`header[0..3]`).

---

## 2. Fontes de Dados

| # | Requisito | Status | Onde está implementado |
|---|---|---|---|
| 2.a | Cada fonte é um **processo separado** | ✅ | 5 binários C independentes (`Makefile`): 2 sensores + 3 atuadores |
| 2.a.i | **Fonte controlável** recebe comandos e reporta estado | ✅ | `camera.c`, `semaforo.c`, `postes.c` — thread TCP recebe `Comando`, responde `RespostaComando` |
| 2.a.ii | **Sensor contínuo** envia leituras periódicas via UDP | ✅ | `sensor_temperatura.c` (15s), `sensor_qualidade_ar.c` (10s) |
| 2.b | Descoberta envia **tipo, IP/porta, estado inicial** | ✅ | `DiscoveryResponse{ source_id, type, ip, udp_port, controllable, status }` |
| 2.c | **Pelo menos uma** fonte controlável | ✅ | 3 fontes controláveis (câmera, semáforo, poste) |

**Eventos relevantes (envio imediato por limiar):** o sensor de CO₂ marca
`alerta=1` quando ultrapassa `limiar_co2`; o semáforo marca alerta em avanço de
sinal — atendendo "imediatamente, quando ocorrer um evento relevante".

---

## 3. Cliente Analítico

| # | Requisito | Status | Onde está implementado |
|---|---|---|---|
| 3.a.i | Conecta ao Gateway via **TCP** | ✅ | `ClienteAnalitico.conectar()` → `Socket(GATEWAY_IP, 6001)` |
| 3.a.ii | Exibe fontes conectadas e seus **estados** | ✅ | Menu opção **1** → `listarFontes()` (mostra tipo, status, controlável) |
| 3.a.iii | Envia comandos para configurar fontes | ✅ | Menu opções **2–5** (ativar, desativar, set_frequencia, set_limiar) |
| 3.b.i | Listar fontes e estados | ✅ | Menu opção **1** |
| 3.b.ii | Ativar/desativar uma fonte | ✅ | Menu opções **2** e **3** |
| 3.b.iii | Consultas agregadas (média, desvio, maior variação) | ✅ | Menu opções **6** (média temp 1h), **7** (desvio CO₂ 24h), **8** (maior variação), **9** (total de alertas) |

> A opção **8 (maior variação)** e **9 (total de alertas)** foram adicionadas ao menu
> CLI para cobrir integralmente o exemplo do requisito 3.b.iii — o Gateway já
> calculava ambas (`db.fonte_maior_variacao`, `db.total_alertas`).

---

## 4. Descoberta de Fontes

| # | Requisito | Status | Onde está implementado |
|---|---|---|---|
| 4.a | Gateway envia multicast ao iniciar | ✅ | `enviar_discovery()` no `main` (e reenvio a cada 30s) |
| 4.b | Fontes respondem com suas informações | ✅ | `DiscoveryResponse` via UDP unicast (sensores) ou TCP (atuadores) |

---

## ➕ Pontuação Extra

| Item | Status | Evidência |
|---|---|---|
| Mais de uma linguagem de programação | ➕ | **Python** (Gateway), **C** (Fontes), **Java** (Cliente) |
| Persistência + consultas de histórico | ➕ | **SQLite** (`db.py`: tabelas `leituras`/`fontes`); rotas `/historico`, `/consultas/*` |
| Cliente com interface gráfica + séries temporais | ➕ | **Dashboard Web** (`dashboard.html` + Chart.js) consumindo a API REST `6003` |

---

## 📋 Pendências de Entrega (não-código)

Estes itens são exigidos na seção **Instruções de Entrega** e dependem da equipe:

- [ ] Slides com detalhes de implementação das 3 partes (formato das mensagens, linguagens, libs)
- [ ] Vídeo de até 7 min (subir processos, executar cliente, simular falha de sensor)
- [ ] `.zip` do código-fonte **ou** link do repositório público no SIGAA
- [ ] Substituir `LINK_DO_VIDEO` no `README.md` pelo link real do YouTube

---

*Resumo: todos os requisitos funcionais (1–4) estão atendidos, mais os 3 itens de
pontuação extra. Restam apenas os artefatos de entrega (slides, vídeo, submissão).*
