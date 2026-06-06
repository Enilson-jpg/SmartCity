import cidade.Cidade.*;   // classes geradas pelo protoc
import java.io.*;
import java.net.*;
import java.util.Scanner;

public class ClienteAnalitico {

    // ── Configuração ──────────────────────────────────────────────────────────
    private static final String GATEWAY_IP   = "127.0.0.1";
    private static final int    GATEWAY_PORT = 6001;  // porta do cliente

    private static Socket       socket;
    private static OutputStream out;
    private static InputStream  in;

    // ── Conecta ao Gateway ────────────────────────────────────────────────────
    public static void conectar() throws IOException {
        socket = new Socket(GATEWAY_IP, GATEWAY_PORT);
        out    = socket.getOutputStream();
        in     = socket.getInputStream();
        System.out.println("[Cliente] Conectado ao Gateway " + GATEWAY_IP);
    }

    // ── Envia mensagem com framing de 4 bytes ─────────────────────────────────
    public static void enviar(byte[] dados) throws IOException {
        byte[] header = new byte[4];
        int len = dados.length;
        header[0] = (byte)((len >> 24) & 0xFF);
        header[1] = (byte)((len >> 16) & 0xFF);
        header[2] = (byte)((len >>  8) & 0xFF);
        header[3] = (byte)((len      ) & 0xFF);
        out.write(header);
        out.write(dados);
        out.flush();
    }

    // ── Recebe mensagem com framing de 4 bytes ────────────────────────────────
    public static byte[] receber() throws IOException {
        byte[] header = in.readNBytes(4);
        int len = ((header[0] & 0xFF) << 24)
                | ((header[1] & 0xFF) << 16)
                | ((header[2] & 0xFF) <<  8)
                | ((header[3] & 0xFF));
        return in.readNBytes(len);
    }

    // ── Comandos do usuário ───────────────────────────────────────────────────
    public static void listarFontes() throws IOException {
        RequisicaoCliente req = RequisicaoCliente.newBuilder()
            .setTipo("listar")
            .build();
        enviar(req.toByteArray());

        byte[] resp_bytes = receber();
        RespostaGateway resp = RespostaGateway.parseFrom(resp_bytes);

        System.out.println("\n=== Fontes Conectadas ===");
        for (DiscoveryResponse fonte : resp.getFontesList()) {
            System.out.printf("  [%s] tipo=%-15s status=%-8s controlável=%s%n",
                fonte.getSourceId(),
                fonte.getType(),
                fonte.getStatus(),
                fonte.getControllable() ? "SIM" : "NÃO");
        }
    }

    public static void enviarComando(String sourceId, String acao, float valor)
            throws IOException {
        Comando cmd = Comando.newBuilder()
            .setSourceId(sourceId)
            .setAcao(acao)
            .setValor(valor)
            .build();

        RequisicaoCliente req = RequisicaoCliente.newBuilder()
            .setTipo("comando")
            .setComando(cmd)
            .build();

        enviar(req.toByteArray());

        byte[] resp_bytes = receber();
        RespostaGateway resp = RespostaGateway.parseFrom(resp_bytes);
        System.out.println("[Comando] " + resp.getResultadoCmd().getMensagem());
    }

    public static void executarConsulta(String consulta) throws IOException {
        RequisicaoCliente req = RequisicaoCliente.newBuilder()
            .setTipo("consulta")
            .setConsulta(consulta)
            .build();
        enviar(req.toByteArray());

        byte[] resp_bytes = receber();
        RespostaGateway resp = RespostaGateway.parseFrom(resp_bytes);
        System.out.println("[Consulta] " + resp.getDadosConsulta());
    }

    // ── Menu interativo ───────────────────────────────────────────────────────
    public static void menu() throws IOException {
        Scanner sc = new Scanner(System.in);
        while (true) {
            System.out.println("""

                ╔══════════════════════════════╗
                ║   Cliente Analítico - UFC    ║
                ╠══════════════════════════════╣
                ║ 1. Listar fontes             ║
                ║ 2. Ativar fonte              ║
                ║ 3. Desativar fonte           ║
                ║ 4. Alterar frequência        ║
                ║ 5. Alterar limiar de alerta  ║
                ║ 6. Consulta: média temp 1h   ║
                ║ 7. Consulta: desvio CO2 24h  ║
                ║ 0. Sair                      ║
                ╚══════════════════════════════╝
                Opção: """);

            String opcao = sc.nextLine().trim();

            switch (opcao) {
                case "1" -> listarFontes();
                case "2" -> {
                    System.out.print("ID da fonte: ");
                    enviarComando(sc.nextLine(), "ativar", 0);
                }
                case "3" -> {
                    System.out.print("ID da fonte: ");
                    enviarComando(sc.nextLine(), "desativar", 0);
                }
                case "4" -> {
                    System.out.print("ID da fonte: ");
                    String id = sc.nextLine();
                    System.out.print("Nova frequência (segundos): ");
                    float freq = Float.parseFloat(sc.nextLine());
                    enviarComando(id, "set_frequencia", freq);
                }
                case "5" -> {
                    System.out.print("ID da fonte: ");
                    String id = sc.nextLine();
                    System.out.print("Novo limiar: ");
                    float lim = Float.parseFloat(sc.nextLine());
                    enviarComando(id, "set_limiar", lim);
                }
                case "6" -> executarConsulta("media_temp_1h");
                case "7" -> executarConsulta("desvio_co2_24h");
                case "0" -> { socket.close(); return; }
                default  -> System.out.println("Opção inválida.");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        conectar();
        menu();
    }
}