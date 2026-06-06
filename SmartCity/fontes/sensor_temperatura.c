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
#define SENSOR_ID "sensor_temp_01"
#define SENSOR_TYPE "temperatura"
#define FREQUENCIA_S 15
#define MINHA_PORTA_UDP 7001

static char gateway_ip[64] = "";
static int gateway_udp_rx = 6002;

// ─── Gera leitura simulada de temperatura (15°C a 40°C) ──────────────────────
static float simular_temperatura(void)
{
    return 15.0f + ((float)(rand() % 2500)) / 100.0f;
}

// ─── Serializa e envia uma Leitura via UDP ────────────────────────────────────
static void enviar_leitura_udp(int sock, struct sockaddr_in *gw_addr)
{
    Cidade__Leitura leitura = CIDADE__LEITURA__INIT;
    leitura.source_id = SENSOR_ID;
    leitura.type = SENSOR_TYPE;
    leitura.timestamp = (int64_t)time(NULL);
    leitura.valor_case = CIDADE__LEITURA__VALOR_TEMPERATURA;
    leitura.temperatura = simular_temperatura();
    leitura.alerta = 0;

    size_t tamanho = cidade__leitura__get_packed_size(&leitura);
    uint8_t *buffer = malloc(tamanho + 4);
    buffer[0] = (tamanho >> 24) & 0xFF;
    buffer[1] = (tamanho >> 16) & 0xFF;
    buffer[2] = (tamanho >> 8) & 0xFF;
    buffer[3] = tamanho & 0xFF;
    cidade__leitura__pack(&leitura, buffer + 4);

    sendto(sock, buffer, tamanho + 4, 0,
           (struct sockaddr *)gw_addr, sizeof(*gw_addr));

    printf("[Temp] Enviado: %.2f°C → %s:%d\n",
           leitura.temperatura, gateway_ip, gateway_udp_rx);

    free(buffer);
}

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

    printf("[Discovery] Aguardando mensagem do Gateway...\n");

    uint8_t buf[1024];
    struct sockaddr_in remetente;
    socklen_t rlen = sizeof(remetente);

    ssize_t n = recvfrom(sock, buf, sizeof(buf), 0,
                         (struct sockaddr *)&remetente, &rlen);
    if (n < 4)
    {
        fprintf(stderr, "[Temp] Anúncio inválido.\n");
        exit(1);
    }

    inet_ntop(AF_INET, &remetente.sin_addr, gateway_ip, sizeof(gateway_ip));

    // ✅ Cast explícito para evitar UB no shift
    uint32_t tamanho = ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) | ((uint32_t)buf[2] << 8) | (uint32_t)buf[3];

    Cidade__DiscoveryRequest *req =
        cidade__discovery_request__unpack(NULL, tamanho, buf + 4);
    if (!req)
    {
        fprintf(stderr, "[Temp] Falha ao desserializar DiscoveryRequest.\n");
        exit(1);
    }

    gateway_udp_rx = req->gateway_port;
    cidade__discovery_request__free_unpacked(req, NULL);
    close(sock);

    printf("[Discovery] Gateway encontrado: %s (UDP RX=%d)\n", gateway_ip, gateway_udp_rx);
}

// ─── Registro: envia DiscoveryResponse via UDP unicast ───────────────────────
static void responder_discovery(void)
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

    size_t tamanho = cidade__discovery_response__get_packed_size(&resp);
    uint8_t *buffer = malloc(tamanho + 4);
    buffer[0] = (tamanho >> 24) & 0xFF;
    buffer[1] = (tamanho >> 16) & 0xFF;
    buffer[2] = (tamanho >> 8) & 0xFF;
    buffer[3] = tamanho & 0xFF;
    cidade__discovery_response__pack(&resp, buffer + 4);

    // ✅ UDP unicast — sem TCP
    struct sockaddr_in gw_addr = {0};
    gw_addr.sin_family = AF_INET;
    gw_addr.sin_port = htons(gateway_udp_rx); // ✅ porta vinda do DiscoveryRequest
    inet_pton(AF_INET, gateway_ip, &gw_addr.sin_addr);

    sendto(sock, buffer, tamanho + 4, 0,
           (struct sockaddr *)&gw_addr, sizeof(gw_addr));

    printf("[Discovery] Registrado no Gateway como '%s' (controllable=0)\n", SENSOR_ID);
    free(buffer);
    close(sock);
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
    responder_discovery(); // Passo 2: envia DiscoveryResponse via UDP unicast

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
        enviar_leitura_udp(udp_sock, &gw_udp);
        sleep(FREQUENCIA_S);
    }

    return 0;
}