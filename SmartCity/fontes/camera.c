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
#define SENSOR_ID "camera_01"
#define SENSOR_TYPE "camera"
#define MINHA_PORTA_UDP 7003

// ─── Estado controlável ───────────────────────────────────────────────────────
static int ativo = 1;
static int frequencia_s = 5;    // envia contagem de pessoas a cada 5s
static int limiar_pessoas = 10; // alerta se detectar mais que isso
static int gravando = 1;        // se 0, câmera parou de gravar

static char gateway_ip[64] = "";
static int gateway_udp_rx = 6002;
static int tcp_fd = -1;

// ─── Simula contagem de pessoas no campo de visão ─────────────────────────────
int simular_contagem()
{
    // Simula entre 0 e 20 pessoas, com picos ocasionais
    int base = rand() % 15;
    if (rand() % 10 == 0)
        base += rand() % 10; // pico de movimento
    return base;
}

// ─── Envia leitura via UDP ────────────────────────────────────────────────────
void enviar_leitura(int sock, struct sockaddr_in *gw, int contagem)
{
    Cidade__Leitura leitura = CIDADE__LEITURA__INIT;
    leitura.source_id = SENSOR_ID;
    leitura.type = SENSOR_TYPE;
    leitura.timestamp = (int64_t)time(NULL);
    leitura.valor_case = CIDADE__LEITURA__VALOR_CONTAGEM;
    leitura.contagem = contagem;
    leitura.alerta = (contagem > limiar_pessoas) ? 1 : 0;

    size_t sz = cidade__leitura__get_packed_size(&leitura);
    uint8_t *buf = malloc(sz + 4);
    buf[0] = (sz >> 24) & 0xFF;
    buf[1] = (sz >> 16) & 0xFF;
    buf[2] = (sz >> 8) & 0xFF;
    buf[3] = sz & 0xFF;
    cidade__leitura__pack(&leitura, buf + 4);

    sendto(sock, buf, sz + 4, 0, (struct sockaddr *)gw, sizeof(*gw));

    if (leitura.alerta)
        printf("[Câmera] AGLOMERAÇÃO! %d pessoas detectadas (limiar=%d)\n",
               contagem, limiar_pessoas);
    else
        printf("[Câmera] %d pessoas no campo de visão\n", contagem);

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
            printf("[Câmera] Conexão perdida.\n");
            break;
        }

        uint32_t sz = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
        recv(tcp_fd, buf, sz, MSG_WAITALL);

        Cidade__Comando *cmd = cidade__comando__unpack(NULL, sz, buf);
        printf("[Câmera] Comando: %s (valor=%.1f)\n", cmd->acao, cmd->valor);

        if (strcmp(cmd->acao, "ativar") == 0)
        {
            ativo = 1;
            gravando = 1;
        }
        else if (strcmp(cmd->acao, "desativar") == 0)
        {
            ativo = 0;
            gravando = 0;
        }
        else if (strcmp(cmd->acao, "set_frequencia") == 0)
            frequencia_s = (int)cmd->valor;
        else if (strcmp(cmd->acao, "set_limiar") == 0)
            limiar_pessoas = (int)cmd->valor;
        else if (strcmp(cmd->acao, "iniciar_gravacao") == 0)
        {
            gravando = 1;
            printf("[Câmera] Gravação iniciada.\n");
        }
        else if (strcmp(cmd->acao, "parar_gravacao") == 0)
        {
            gravando = 0;
            printf("[Câmera] Gravação pausada.\n");
        }

        // Envia RespostaComando ao Gateway
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

// ─── Discovery: escuta multicast e se registra no Gateway ─────────────────────
void descobrir_e_registrar()
{
    // 1) Escuta multicast
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

    printf("[Câmera] Aguardando Gateway via multicast...\n");

    uint8_t buf[512];
    struct sockaddr_in remetente;
    socklen_t rlen = sizeof(remetente);
    recvfrom(mcast_sock, buf, sizeof(buf), 0,
             (struct sockaddr *)&remetente, &rlen);

    // IP real do gateway = quem mandou o multicast
    inet_ntop(AF_INET, &remetente.sin_addr, gateway_ip, sizeof(gateway_ip));

    uint32_t sz = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
    Cidade__DiscoveryRequest *req =
        cidade__discovery_request__unpack(NULL, sz, buf + 4);
    int gateway_tcp_port = req->gateway_port;
    cidade__discovery_request__free_unpacked(req, NULL);
    close(mcast_sock);

    printf("[Câmera] Gateway em %s:%d\n", gateway_ip, gateway_tcp_port);

    // 2) Conecta via TCP e envia DiscoveryResponse
    tcp_fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in gw_tcp = {0};
    gw_tcp.sin_family = AF_INET;
    gw_tcp.sin_port = htons(gateway_tcp_port);
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

    printf("[Câmera] Registrada no Gateway.\n");
}

// ─── Main ─────────────────────────────────────────────────────────────────────
int main(int argc, char *argv[])
{
    srand(time(NULL));
    if (argc >= 3) {
        strncpy(gateway_ip, argv[1], sizeof(gateway_ip) - 1);
        int gw_tcp_port = atoi(argv[2]);
        /* Conecta diretamente via TCP, sem multicast */
        tcp_fd = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in gw_tcp = {0};
        gw_tcp.sin_family = AF_INET;
        gw_tcp.sin_port = htons(gw_tcp_port);
        inet_pton(AF_INET, gateway_ip, &gw_tcp.sin_addr);
        if (connect(tcp_fd, (struct sockaddr *)&gw_tcp, sizeof(gw_tcp)) < 0) {
            perror("[Câmera] connect TCP");
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
        printf("[Câmera] Registrada no Gateway %s:%d\n", gateway_ip, gw_tcp_port);
    } else {
        descobrir_e_registrar();
    }

    // Thread de comandos
    pthread_t t;
    pthread_create(&t, NULL, thread_comandos, NULL);

    // Socket UDP para leituras
    int udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in gw_udp = {0};
    gw_udp.sin_family = AF_INET;
    gw_udp.sin_port = htons(gateway_udp_rx);
    inet_pton(AF_INET, gateway_ip, &gw_udp.sin_addr);

    while (1)
    {
        if (ativo && gravando)
        {
            int contagem = simular_contagem();
            enviar_leitura(udp_sock, &gw_udp, contagem);
        }
        else
        {
            printf("[Câmera] Inativa / não gravando.\n");
        }
        sleep(frequencia_s);
    }
    return 0;
}