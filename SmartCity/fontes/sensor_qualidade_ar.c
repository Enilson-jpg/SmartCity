#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include "cidade.pb-c.h"

// ─── Configurações ────────────────────────────────────────────────────────────
#define MULTICAST_GROUP "224.1.1.1"
#define MULTICAST_PORT 5007
#define SENSOR_ID "sensor_co2_01"
#define SENSOR_TYPE "qualidade_ar"
#define FREQUENCIA_S 10
#define MINHA_PORTA_UDP 7002

static float limiar_co2 = 800.0f;
static char gateway_ip[64] = "";
static int gateway_udp_rx = 6002;

// ─── Discovery: escuta multicast e descobre o Gateway ────────────────────────
static void descobrir_gateway(void)
{
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0)
    {
        perror("socket multicast");
        exit(1);
    }

    int reuse = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(MULTICAST_PORT);
    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    {
        perror("bind multicast");
        exit(1);
    }

    struct ip_mreq mreq;
    mreq.imr_multiaddr.s_addr = inet_addr(MULTICAST_GROUP);
    mreq.imr_interface.s_addr = htonl(INADDR_ANY);
    setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));

    printf("[CO2] Aguardando anúncio do Gateway em %s:%d …\n",
           MULTICAST_GROUP, MULTICAST_PORT);

    uint8_t buf[1024];
    struct sockaddr_in remetente;
    socklen_t rlen = sizeof(remetente);

    ssize_t n = recvfrom(sock, buf, sizeof(buf), 0,
                         (struct sockaddr *)&remetente, &rlen);
    if (n < 4)
    {
        fprintf(stderr, "[CO2] Anúncio inválido.\n");
        exit(1);
    }

    // Extrai IP real do gateway
    inet_ntop(AF_INET, &remetente.sin_addr, gateway_ip, sizeof(gateway_ip));

    // Desserializa o DiscoveryRequest
    uint32_t tamanho = ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) | ((uint32_t)buf[2] << 8) | (uint32_t)buf[3];

    Cidade__DiscoveryRequest *req =
        cidade__discovery_request__unpack(NULL, tamanho, buf + 4);
    if (!req)
    {
        fprintf(stderr, "[CO2] Falha ao desserializar DiscoveryRequest.\n");
        exit(1);
    }

    gateway_udp_rx = req->gateway_port;
    cidade__discovery_request__free_unpacked(req, NULL);
    close(sock);

    printf("[CO2] Gateway encontrado: %s (UDP RX=%d)\n", gateway_ip, gateway_udp_rx);
}

// ─── Registro: envia DiscoveryResponse via UDP unicast ───────────────────────
static void registrar_no_gateway(void)
{
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0)
    {
        perror("socket UDP registro");
        exit(1);
    }

    Cidade__DiscoveryResponse resp = CIDADE__DISCOVERY_RESPONSE__INIT;
    resp.source_id = SENSOR_ID;
    resp.type = SENSOR_TYPE;
    resp.ip = "0.0.0.0";
    resp.udp_port = MINHA_PORTA_UDP;
    resp.controllable = 0; // sensor contínuo — não é controlável
    resp.status = "ativo";

    size_t sz = cidade__discovery_response__get_packed_size(&resp);
    uint8_t *buf = malloc(sz + 4);
    buf[0] = (sz >> 24) & 0xFF;
    buf[1] = (sz >> 16) & 0xFF;
    buf[2] = (sz >> 8) & 0xFF;
    buf[3] = sz & 0xFF;
    cidade__discovery_response__pack(&resp, buf + 4);

    struct sockaddr_in gw_addr = {0};
    gw_addr.sin_family = AF_INET;
    gw_addr.sin_port = htons(gateway_udp_rx);
    inet_pton(AF_INET, gateway_ip, &gw_addr.sin_addr);

    sendto(sock, buf, sz + 4, 0,
           (struct sockaddr *)&gw_addr, sizeof(gw_addr));

    printf("[CO2] Registrado no Gateway como '%s' (controllable=0)\n", SENSOR_ID);
    free(buf);
    close(sock);
}

// ─── Envia leitura de CO2 via UDP ─────────────────────────────────────────────
static void enviar_co2(int sock, struct sockaddr_in *gw_addr, float co2)
{
    Cidade__Leitura leitura = CIDADE__LEITURA__INIT;
    leitura.source_id = SENSOR_ID;
    leitura.type = SENSOR_TYPE;
    leitura.timestamp = (int64_t)time(NULL);
    leitura.valor_case = CIDADE__LEITURA__VALOR_CO2;
    leitura.co2 = co2;
    leitura.alerta = (co2 > limiar_co2) ? 1 : 0;

    size_t sz = cidade__leitura__get_packed_size(&leitura);
    uint8_t *buf = malloc(sz + 4);
    buf[0] = (sz >> 24) & 0xFF;
    buf[1] = (sz >> 16) & 0xFF;
    buf[2] = (sz >> 8) & 0xFF;
    buf[3] = sz & 0xFF;
    cidade__leitura__pack(&leitura, buf + 4);

    sendto(sock, buf, sz + 4, 0,
           (struct sockaddr *)gw_addr, sizeof(*gw_addr));
    free(buf);

    if (leitura.alerta)
        printf("\033[33m[CO2] ALERTA! CO2=%.1f ppm (limiar=%.1f)\033[0m\n",
               co2, limiar_co2);
    else
        printf("[CO2] Leitura: %.1f ppm → %s:%d\n", co2, gateway_ip, gateway_udp_rx);
}

// ─── Main ─────────────────────────────────────────────────────────────────────
int main(int argc, char *argv[])
{
    srand((unsigned)time(NULL));

    if (argc >= 3) {
        strncpy(gateway_ip, argv[1], sizeof(gateway_ip) - 1);
        gateway_udp_rx = atoi(argv[2]);
        printf("[Discovery] Gateway via argumento: %s:%d\n", gateway_ip, gateway_udp_rx);
    } else {
        descobrir_gateway(); // Passo 1: escuta multicast, descobre IP/porta do gateway
    }
    registrar_no_gateway(); // Passo 2: envia DiscoveryResponse via UDP unicast

    // Passo 3: socket UDP para envio periódico de leituras
    int udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (udp_sock < 0)
    {
        perror("socket UDP leituras");
        exit(1);
    }

    struct sockaddr_in gw_udp = {0};
    gw_udp.sin_family = AF_INET;
    gw_udp.sin_port = htons(gateway_udp_rx);
    inet_pton(AF_INET, gateway_ip, &gw_udp.sin_addr);

    // Passo 4: loop contínuo de envio
    while (1)
    {
        float co2 = 400.0f + ((float)(rand() % 80000)) / 100.0f;
        enviar_co2(udp_sock, &gw_udp, co2);
        sleep(FREQUENCIA_S);
    }

    return 0;
}