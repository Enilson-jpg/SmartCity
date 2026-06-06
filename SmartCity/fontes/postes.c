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

#define MULTICAST_GROUP "224.1.1.1"
#define MULTICAST_PORT 5007
#define SENSOR_ID "poste_01"
#define SENSOR_TYPE "poste"
#define MINHA_PORTA_UDP 7004

// ─── Estado controlável ───────────────────────────────────────────────────────
static int ativo = 1;
static int frequencia_s = 10;
static float intensidade = 100.0f; // % de brilho (0 a 100)
static float limiar_lux = 50.0f;   // liga automaticamente abaixo desse lux
static int modo_auto = 1;          // 1=automático, 0=manual

static char gateway_ip[64] = "";
static int gateway_udp_rx = 6002;
static int tcp_fd = -1;

// ─── Simula luminosidade ambiente (lux) ───────────────────────────────────────
// Varia ao longo do dia: baixo à noite, alto durante o dia
float simular_luminosidade()
{
    time_t agora = time(NULL);
    struct tm *t = localtime(&agora);
    int hora = t->tm_hour;

    // Noite (18h-6h): 0-80 lux | Dia (6h-18h): 200-1000 lux
    if (hora >= 18 || hora < 6)
        return (float)(rand() % 80);
    else
        return 200.0f + (float)(rand() % 800);
}

// ─── Envia leitura via UDP ────────────────────────────────────────────────────
void enviar_leitura(int sock, struct sockaddr_in *gw, float lux)
{
    // Lógica automática: liga/desliga baseado na luminosidade
    if (modo_auto)
    {
        ativo = (lux < limiar_lux) ? 1 : 0;
    }

    Cidade__Leitura leitura = CIDADE__LEITURA__INIT;
    leitura.source_id = SENSOR_ID;
    leitura.type = SENSOR_TYPE;
    leitura.timestamp = (int64_t)time(NULL);
    leitura.valor_case = CIDADE__LEITURA__VALOR_ENERGIA;
    // Reporta consumo energético: intensidade × fator base
    leitura.energia = ativo ? (intensidade / 100.0f) * 150.0f : 0.0f; // watts
    leitura.alerta = (!ativo && lux < limiar_lux && !modo_auto) ? 1 : 0;

    size_t sz = cidade__leitura__get_packed_size(&leitura);
    uint8_t *buf = malloc(sz + 4);
    buf[0] = (sz >> 24) & 0xFF;
    buf[1] = (sz >> 16) & 0xFF;
    buf[2] = (sz >> 8) & 0xFF;
    buf[3] = sz & 0xFF;
    cidade__leitura__pack(&leitura, buf + 4);
    sendto(sock, buf, sz + 4, 0, (struct sockaddr *)gw, sizeof(*gw));

    printf("[Poste] Lux=%.1f | Estado=%s | Intensidade=%.0f%% | Consumo=%.1fW\n",
           lux,
           ativo ? "LIGADO" : "DESLIGADO",
           intensidade,
           leitura.energia);

    free(buf);
}

// ─── Thread: escuta comandos TCP do Gateway ───────────────────────────────────
void *thread_comandos(void *arg)
{
    uint8_t buf[1024];
    while (1)
    {
        ssize_t n = recv(tcp_fd, buf, 4, MSG_WAITALL);
        if (n <= 0)
        {
            printf("[Poste] Conexão perdida.\n");
            break;
        }

        uint32_t sz = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
        recv(tcp_fd, buf, sz, MSG_WAITALL);

        Cidade__Comando *cmd = cidade__comando__unpack(NULL, sz, buf);
        printf("[Poste] Comando: %s (valor=%.1f)\n", cmd->acao, cmd->valor);

        if (strcmp(cmd->acao, "ativar") == 0)
        {
            ativo = 1;
            modo_auto = 0;
        }
        else if (strcmp(cmd->acao, "desativar") == 0)
        {
            ativo = 0;
            modo_auto = 0;
        }
        else if (strcmp(cmd->acao, "set_intensidade") == 0)
        {
            intensidade = cmd->valor;
            if (intensidade < 0)
                intensidade = 0;
            if (intensidade > 100)
                intensidade = 100;
            printf("[Poste] Intensidade ajustada para %.0f%%\n", intensidade);
        }
        else if (strcmp(cmd->acao, "set_limiar") == 0)
        {
            limiar_lux = cmd->valor;
            printf("[Poste] Novo limiar de luminosidade: %.1f lux\n", limiar_lux);
        }
        else if (strcmp(cmd->acao, "modo_auto") == 0)
        {
            modo_auto = (int)cmd->valor; // 1=auto, 0=manual
            printf("[Poste] Modo: %s\n", modo_auto ? "automático" : "manual");
        }
        else if (strcmp(cmd->acao, "set_frequencia") == 0)
            frequencia_s = (int)cmd->valor;

        // Resposta
        Cidade__RespostaComando resp = CIDADE__RESPOSTA_COMANDO__INIT;
        resp.sucesso = 1;
        resp.mensagem = "Comando aplicado";

        size_t rsz = cidade__resposta_comando__get_packed_size(&resp);
        uint8_t *rbuf = malloc(rsz + 4);
        rbuf[0] = (rsz >> 24) & 0xFF;
        rbuf[1] = (rsz >> 16) & 0xFF;
        rbuf[2] = (rsz >> 8) & 0xFF;
        rbuf[3] = rsz & 0xFF;
        cidade__resposta_comando__pack(&resp, rbuf + 4);
        send(tcp_fd, rbuf, rsz + 4, 0);
        free(rbuf);

        cidade__comando__free_unpacked(cmd, NULL);
    }
    return NULL;
}

// ─── Discovery (igual à câmera) ───────────────────────────────────────────────
void descobrir_e_registrar()
{
    int mcast_sock = socket(AF_INET, SOCK_DGRAM, 0);
    int reuse = 1;
    setsockopt(mcast_sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(MULTICAST_PORT);
    bind(mcast_sock, (struct sockaddr *)&addr, sizeof(addr));

    struct ip_mreq mreq;
    mreq.imr_multiaddr.s_addr = inet_addr(MULTICAST_GROUP);
    mreq.imr_interface.s_addr = htonl(INADDR_ANY);
    setsockopt(mcast_sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));

    printf("[Poste] Aguardando Gateway via multicast...\n");

    uint8_t buf[512];
    struct sockaddr_in remetente;
    socklen_t rlen = sizeof(remetente);
    recvfrom(mcast_sock, buf, sizeof(buf), 0,
             (struct sockaddr *)&remetente, &rlen);

    inet_ntop(AF_INET, &remetente.sin_addr, gateway_ip, sizeof(gateway_ip));

    uint32_t sz = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
    Cidade__DiscoveryRequest *req =
        cidade__discovery_request__unpack(NULL, sz, buf + 4);
    int gw_tcp_port = req->gateway_port;
    cidade__discovery_request__free_unpacked(req, NULL);
    close(mcast_sock);

    printf("[Poste] Gateway em %s:%d\n", gateway_ip, gw_tcp_port);

    tcp_fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in gw_tcp = {0};
    gw_tcp.sin_family = AF_INET;
    gw_tcp.sin_port = htons(gw_tcp_port);
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

    printf("[Poste] Registrado no Gateway.\n");
}

// ─── Main ─────────────────────────────────────────────────────────────────────
int main(int argc, char *argv[])
{
    srand(time(NULL));
    if (argc >= 3) {
        strncpy(gateway_ip, argv[1], sizeof(gateway_ip) - 1);
        int gw_tcp_port = atoi(argv[2]);
        tcp_fd = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in gw_tcp = {0};
        gw_tcp.sin_family = AF_INET;
        gw_tcp.sin_port = htons(gw_tcp_port);
        inet_pton(AF_INET, gateway_ip, &gw_tcp.sin_addr);
        if (connect(tcp_fd, (struct sockaddr *)&gw_tcp, sizeof(gw_tcp)) < 0) {
            perror("[Poste] connect TCP");
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
        printf("[Poste] Registrado no Gateway %s:%d\n", gateway_ip, gw_tcp_port);
    } else {
        descobrir_e_registrar();
    }

    pthread_t t;
    pthread_create(&t, NULL, thread_comandos, NULL);

    int udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in gw_udp = {0};
    gw_udp.sin_family = AF_INET;
    gw_udp.sin_port = htons(gateway_udp_rx);
    inet_pton(AF_INET, gateway_ip, &gw_udp.sin_addr);

    while (1)
    {
        float lux = simular_luminosidade();
        enviar_leitura(udp_sock, &gw_udp, lux);
        sleep(frequencia_s);
    }
    return 0;
}