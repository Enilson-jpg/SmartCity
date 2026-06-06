#define _GNU_SOURCE /* garante extensões POSIX/GNU no GCC */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <sys/types.h>  /* tipos base (uint8_t, etc.) */
#include <sys/socket.h> /* socket(), bind(), etc.     */
#include <netinet/in.h> /* struct ip_mreq, IPPROTO_IP */
#include <arpa/inet.h>  /* inet_addr, inet_pton       */
#include "cidade.pb-c.h"

/* ─── Configurações ─────────────────────────────────────────────────────────── */
#define MULTICAST_GROUP "224.1.1.1"
#define MULTICAST_PORT 5007
#define SENSOR_ID "semaforo_01"
#define SENSOR_TYPE "semaforo"
#define MINHA_PORTA_UDP 7005
#define GATEWAY_TCP_PORT 6000

/*
 * O semáforo reporta como "contagem" o fluxo de veículos
 * que passa durante o ciclo verde.
 * Estados internos: 0=VERMELHO, 1=AMARELO, 2=VERDE
 */
#define ESTADO_VERMELHO 0
#define ESTADO_AMARELO 1
#define ESTADO_VERDE 2

/* ─── Estado controlável ────────────────────────────────────────────────────── */
static int ativo = 1;
static int frequencia_s = 8;    /* duração de cada fase (segundos) */
static int modo_emergencia = 0; /* 1 = pisca amarelo contínuo      */
static int estado_atual = ESTADO_VERDE;

/* Duração de cada fase (configurável) */
static int tempo_verde_s = 30;
static int tempo_amarelo_s = 5;
static int tempo_vermelho_s = 30;

static char gateway_ip[64] = "";
static int gateway_udp_rx = 6002;
static int tcp_fd = -1;

/* ─── Simula fluxo de veículos dependendo do estado ────────────────────────── */
int simular_fluxo()
{
    switch (estado_atual)
    {
    case ESTADO_VERDE:
        return 5 + rand() % 20; /* tráfego passando   */
    case ESTADO_AMARELO:
        return 0 + rand() % 5; /* poucos passam      */
    case ESTADO_VERMELHO:
        return 0; /* ninguém passa      */
    default:
        return 0;
    }
}

static const char *nome_estado(int e)
{
    switch (e)
    {
    case ESTADO_VERDE:
        return "VERDE";
    case ESTADO_AMARELO:
        return "AMARELO";
    case ESTADO_VERMELHO:
        return "VERMELHO";
    default:
        return "DESCONHECIDO";
    }
}

/* ─── Envia leitura via UDP ─────────────────────────────────────────────────── */
void enviar_leitura(int sock, struct sockaddr_in *gw, int fluxo)
{
    Cidade__Leitura leitura = CIDADE__LEITURA__INIT;
    leitura.source_id = SENSOR_ID;
    leitura.type = SENSOR_TYPE;
    leitura.timestamp = (int64_t)time(NULL);
    leitura.valor_case = CIDADE__LEITURA__VALOR_CONTAGEM;
    leitura.contagem = fluxo;
    /* Alerta se fluxo alto no vermelho (possível invasão de sinal) */
    leitura.alerta = (estado_atual == ESTADO_VERMELHO && fluxo > 2) ? 1 : 0;

    size_t sz = cidade__leitura__get_packed_size(&leitura);
    uint8_t *buf = malloc(sz + 4);
    buf[0] = (sz >> 24) & 0xFF;
    buf[1] = (sz >> 16) & 0xFF;
    buf[2] = (sz >> 8) & 0xFF;
    buf[3] = sz & 0xFF;
    cidade__leitura__pack(&leitura, buf + 4);
    sendto(sock, buf, sz + 4, 0, (struct sockaddr *)gw, sizeof(*gw));

    if (leitura.alerta)
        printf("[Semaforo] ALERTA! Possivel avanco de sinal! Fluxo=%d\n", fluxo);
    else
        printf("[Semaforo] Estado=%-8s | Fluxo=%d veiculos\n",
               nome_estado(estado_atual), fluxo);

    free(buf);
}

/* ─── Envia RespostaComando ao Gateway ──────────────────────────────────────── */
void enviar_resposta(int sucesso, const char *mensagem)
{
    Cidade__RespostaComando resp = CIDADE__RESPOSTA_COMANDO__INIT;
    resp.sucesso = sucesso;
    resp.mensagem = (char *)mensagem;

    size_t rsz = cidade__resposta_comando__get_packed_size(&resp);
    uint8_t *rbuf = malloc(rsz + 4);
    rbuf[0] = (rsz >> 24) & 0xFF;
    rbuf[1] = (rsz >> 16) & 0xFF;
    rbuf[2] = (rsz >> 8) & 0xFF;
    rbuf[3] = rsz & 0xFF;
    cidade__resposta_comando__pack(&resp, rbuf + 4);
    send(tcp_fd, rbuf, rsz + 4, 0);
    free(rbuf);
}

/* ─── Thread: escuta comandos TCP do Gateway ────────────────────────────────── */
void *thread_comandos(void *arg)
{
    (void)arg;
    uint8_t buf[1024];

    while (1)
    {
        ssize_t n = recv(tcp_fd, buf, 4, MSG_WAITALL);
        if (n <= 0)
        {
            printf("[Semaforo] Conexao com Gateway perdida.\n");
            break;
        }

        uint32_t sz = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
        recv(tcp_fd, buf, sz, MSG_WAITALL);

        Cidade__Comando *cmd = cidade__comando__unpack(NULL, sz, buf);
        printf("[Semaforo] Comando: %s (valor=%.1f)\n", cmd->acao, cmd->valor);

        if (strcmp(cmd->acao, "ativar") == 0)
        {
            ativo = 1;
            modo_emergencia = 0;
            estado_atual = ESTADO_VERDE;
            printf("[Semaforo] Semaforo ativado.\n");
            enviar_resposta(1, "Semaforo ativado");
        }
        else if (strcmp(cmd->acao, "desativar") == 0)
        {
            ativo = 0;
            printf("[Semaforo] Semaforo desativado.\n");
            enviar_resposta(1, "Semaforo desativado");
        }
        else if (strcmp(cmd->acao, "modo_emergencia") == 0)
        {
            modo_emergencia = (int)cmd->valor; /* 1=ativar, 0=desativar */
            if (modo_emergencia)
            {
                estado_atual = ESTADO_AMARELO;
                printf("[Semaforo] MODO EMERGENCIA ativado (pisca amarelo).\n");
                enviar_resposta(1, "Modo emergencia ativado");
            }
            else
            {
                estado_atual = ESTADO_VERDE;
                printf("[Semaforo] Modo emergencia desativado.\n");
                enviar_resposta(1, "Modo emergencia desativado");
            }
        }
        else if (strcmp(cmd->acao, "set_tempo_verde") == 0)
        {
            tempo_verde_s = (int)cmd->valor;
            printf("[Semaforo] Tempo verde: %ds\n", tempo_verde_s);
            enviar_resposta(1, "Tempo verde atualizado");
        }
        else if (strcmp(cmd->acao, "set_tempo_vermelho") == 0)
        {
            tempo_vermelho_s = (int)cmd->valor;
            printf("[Semaforo] Tempo vermelho: %ds\n", tempo_vermelho_s);
            enviar_resposta(1, "Tempo vermelho atualizado");
        }
        else if (strcmp(cmd->acao, "set_frequencia") == 0)
        {
            frequencia_s = (int)cmd->valor;
            printf("[Semaforo] Frequencia de reporte: %ds\n", frequencia_s);
            enviar_resposta(1, "Frequencia atualizada");
        }
        else
        {
            enviar_resposta(0, "Comando desconhecido");
        }

        cidade__comando__free_unpacked(cmd, NULL);
    }
    return NULL;
}

/* ─── Thread: ciclo do semáforo ─────────────────────────────────────────────── */
void *thread_ciclo(void *arg)
{
    (void)arg;
    while (1)
    {
        if (!ativo)
        {
            sleep(1);
            continue;
        }

        if (modo_emergencia)
        {
            /* Pisca amarelo: alterna estado a cada 1 segundo */
            estado_atual = (estado_atual == ESTADO_AMARELO)
                               ? ESTADO_VERMELHO
                               : ESTADO_AMARELO;
            sleep(1);
            continue;
        }

        /* Ciclo normal: VERDE → AMARELO → VERMELHO → VERDE ... */
        estado_atual = ESTADO_VERDE;
        sleep(tempo_verde_s);

        if (!ativo || modo_emergencia)
            continue;
        estado_atual = ESTADO_AMARELO;
        sleep(tempo_amarelo_s);

        if (!ativo || modo_emergencia)
            continue;
        estado_atual = ESTADO_VERMELHO;
        sleep(tempo_vermelho_s);
    }
    return NULL;
}

/* ─── Discovery ─────────────────────────────────────────────────────────────── */
void descobrir_e_registrar()
{
    int mcast_sock = socket(AF_INET, SOCK_DGRAM, 0);
    int reuse = 1;
    setsockopt(mcast_sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(MULTICAST_PORT);
    bind(mcast_sock, (struct sockaddr *)&addr, sizeof(addr));

    struct ip_mreq mreq;
    mreq.imr_multiaddr.s_addr = inet_addr(MULTICAST_GROUP);
    mreq.imr_interface.s_addr = htonl(INADDR_ANY);
    setsockopt(mcast_sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));

    printf("[Semaforo] Aguardando Gateway via multicast...\n");

    uint8_t buf[512];
    struct sockaddr_in remetente;
    socklen_t rlen = sizeof(remetente);
    recvfrom(mcast_sock, buf, sizeof(buf), 0,
             (struct sockaddr *)&remetente, &rlen);

    inet_ntop(AF_INET, &remetente.sin_addr, gateway_ip, sizeof(gateway_ip));

    uint32_t sz = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
    Cidade__DiscoveryRequest *req =
        cidade__discovery_request__unpack(NULL, sz, buf + 4);
    gateway_udp_rx = req->gateway_port;
    cidade__discovery_request__free_unpacked(req, NULL);
    close(mcast_sock);

    printf("[Semaforo] Gateway em %s\n", gateway_ip);

    tcp_fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in gw_tcp;
    memset(&gw_tcp, 0, sizeof(gw_tcp));
    gw_tcp.sin_family = AF_INET;
    gw_tcp.sin_port = htons(GATEWAY_TCP_PORT);
    inet_pton(AF_INET, gateway_ip, &gw_tcp.sin_addr);
    connect(tcp_fd, (struct sockaddr *)&gw_tcp, sizeof(gw_tcp));

    Cidade__DiscoveryResponse resp = CIDADE__DISCOVERY_RESPONSE__INIT;
    resp.source_id = SENSOR_ID;
    resp.type = SENSOR_TYPE;
    resp.ip = gateway_ip;
    resp.udp_port = MINHA_PORTA_UDP;
    resp.controllable = 1;
    resp.status = "ativo";

    size_t rsz = cidade__discovery_response__get_packed_size(&resp);
    uint8_t *rbuf = malloc(rsz + 4);
    rbuf[0] = (rsz >> 24) & 0xFF;
    rbuf[1] = (rsz >> 16) & 0xFF;
    rbuf[2] = (rsz >> 8) & 0xFF;
    rbuf[3] = rsz & 0xFF;
    cidade__discovery_response__pack(&resp, rbuf + 4);
    send(tcp_fd, rbuf, rsz + 4, 0);
    free(rbuf);

    printf("[Semaforo] Registrado no Gateway.\n");
}

/* ─── Main ──────────────────────────────────────────────────────────────────── */
int main(int argc, char *argv[])
{
    srand((unsigned int)time(NULL));
    if (argc >= 3) {
        strncpy(gateway_ip, argv[1], sizeof(gateway_ip) - 1);
        int gw_tcp_port = atoi(argv[2]);
        tcp_fd = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in gw_tcp;
        memset(&gw_tcp, 0, sizeof(gw_tcp));
        gw_tcp.sin_family = AF_INET;
        gw_tcp.sin_port = htons(gw_tcp_port);
        inet_pton(AF_INET, gateway_ip, &gw_tcp.sin_addr);
        if (connect(tcp_fd, (struct sockaddr *)&gw_tcp, sizeof(gw_tcp)) < 0) {
            perror("[Semaforo] connect TCP");
            exit(1);
        }
        Cidade__DiscoveryResponse resp = CIDADE__DISCOVERY_RESPONSE__INIT;
        resp.source_id = SENSOR_ID;
        resp.type = SENSOR_TYPE;
        resp.ip = gateway_ip;
        resp.udp_port = MINHA_PORTA_UDP;
        resp.controllable = 1;
        resp.status = "ativo";
        size_t rsz = cidade__discovery_response__get_packed_size(&resp);
        uint8_t *rbuf = malloc(rsz + 4);
        rbuf[0] = (rsz >> 24) & 0xFF;
        rbuf[1] = (rsz >> 16) & 0xFF;
        rbuf[2] = (rsz >> 8) & 0xFF;
        rbuf[3] = rsz & 0xFF;
        cidade__discovery_response__pack(&resp, rbuf + 4);
        send(tcp_fd, rbuf, rsz + 4, 0);
        free(rbuf);
        printf("[Semaforo] Registrado no Gateway %s:%d\n", gateway_ip, gw_tcp_port);
    } else {
        descobrir_e_registrar();
    }

    /* Thread de comandos TCP */
    pthread_t t_cmd;
    pthread_create(&t_cmd, NULL, thread_comandos, NULL);

    /* Thread do ciclo semafórico */
    pthread_t t_ciclo;
    pthread_create(&t_ciclo, NULL, thread_ciclo, NULL);

    /* Socket UDP para enviar leituras ao Gateway */
    int udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in gw_udp;
    memset(&gw_udp, 0, sizeof(gw_udp));
    gw_udp.sin_family = AF_INET;
    gw_udp.sin_port = htons(gateway_udp_rx);
    inet_pton(AF_INET, gateway_ip, &gw_udp.sin_addr);

    /* Loop principal: reporta fluxo periodicamente */
    while (1)
    {
        if (ativo)
        {
            int fluxo = simular_fluxo();
            enviar_leitura(udp_sock, &gw_udp, fluxo);
        }
        else
        {
            printf("[Semaforo] Inativo.\n");
        }
        sleep(frequencia_s);
    }
    return 0;
}