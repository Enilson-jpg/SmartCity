# ─────────────────────────────────────────────────────────────────────────────
#  SmartCity · Painel de Controle
#  Motor em PowerShell (cores nativas, REST nativo, tabelas limpas).
#  Lancado pelo menu.bat
# ─────────────────────────────────────────────────────────────────────────────

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$Host.UI.RawUI.WindowTitle = 'SmartCity · Painel de Controle'

# ── Caminhos ─────────────────────────────────────────────────────────────────
# Tudo derivado da pasta onde este script esta (raiz do repositorio), para que
# o painel funcione em qualquer clone, independente de usuario ou local.

# Converte um caminho Windows (C:\...) para o formato WSL (/mnt/c/...).
function To-WslPath {
    param([string]$WinPath)
    $p = $WinPath -replace '\\', '/'
    if ($p -match '^([A-Za-z]):/(.*)$') { return "/mnt/$($Matches[1].ToLower())/$($Matches[2])" }
    return $p
}

$Root    = $PSScriptRoot
$Proj    = Join-Path $Root 'SmartCity'
$Dash    = Join-Path $Proj 'cliente\dashboard.html'

$ProjWsl = To-WslPath $Proj
$DemoWsl = "$ProjWsl/fontes"

# 127.0.0.1 (nao 'localhost'): em WSL2 mirrored, 'localhost' resolve IPv6 (::1)
# e o gateway escuta so em IPv4 -> usar o IP literal garante alcance do Windows.
$Api     = 'http://127.0.0.1:6003'

# Gateway roda DENTRO do WSL (mesmo Linux das fontes -> discovery multicast nativo).
$GwDirWsl = "$ProjWsl/gateway"
$GwPyWsl  = "$ProjWsl/.venv-wsl/bin/python"

# Mapa source_id -> nome do binario no WSL (para matar processo nas falhas)
$BinMap = @{
    'sensor_temp_01' = 'sensor_temperatura'
    'sensor_co2_01'  = 'sensor_qualidade_ar'
    'camera_01'      = 'camera'
    'semaforo_01'    = 'semaforo'
    'poste_01'       = 'poste'
}

# ═════════════════════════════════════════════════════════════════════════════
#  HELPERS DE INTERFACE
# ═════════════════════════════════════════════════════════════════════════════

function Get-Status {
    try {
        $r = Invoke-RestMethod "$Api/fontes" -TimeoutSec 1
        return [pscustomobject]@{ Online = $true; Count = @($r).Count }
    } catch {
        return [pscustomobject]@{ Online = $false; Count = 0 }
    }
}

# Busca um array JSON da API de forma confiavel.
# IMPORTANTE: a variavel intermediaria ($resp) e obrigatoria. Fazer
# @(Invoke-RestMethod ...) direto faz o PowerShell embrulhar o array inteiro
# num unico elemento (Count=1 e propriedades viram System.Object[]).
function Get-Json {
    param([string]$Path)
    $resp = Invoke-RestMethod "$Api$Path"
    return @($resp)
}

function Write-Banner {
    param([string]$Text, [int]$Width = 50)
    $line = ([string]([char]0x2550)) * $Width
    $pad  = $Width - $Text.Length
    $l    = [math]::Floor($pad / 2)
    $r    = $pad - $l
    Write-Host ''
    Write-Host ("  " + [char]0x2554 + $line + [char]0x2557) -ForegroundColor Cyan
    Write-Host ("  " + [char]0x2551 + (' ' * $l)) -NoNewline -ForegroundColor Cyan
    Write-Host $Text -NoNewline -ForegroundColor White
    Write-Host ((' ' * $r) + [char]0x2551) -ForegroundColor Cyan
    Write-Host ("  " + [char]0x255A + $line + [char]0x255D) -ForegroundColor Cyan
}

function Write-Section {
    param([string]$Label)
    $dash = ([string]([char]0x2500))
    $line = $dash * [math]::Max(2, 48 - $Label.Length)
    Write-Host ''
    Write-Host ("  " + $dash + $dash + " ") -NoNewline -ForegroundColor DarkCyan
    Write-Host $Label -NoNewline -ForegroundColor Yellow
    Write-Host (" " + $line) -ForegroundColor DarkCyan
}

function Show-Section {
    param([string]$Title)
    Clear-Host
    Write-Banner $Title
    Write-Host ''
}

function Pause-Menu {
    Write-Host ''
    Write-Host '   Pressione ENTER para voltar ao menu...' -ForegroundColor DarkGray
    [void](Read-Host)
}

function Require-Gateway {
    param($Status)
    if (-not $Status.Online) {
        Write-Host '   Gateway esta OFFLINE. Inicie com a opcao [1] primeiro.' -ForegroundColor Red
        Pause-Menu
        return $false
    }
    return $true
}

# Formata um valor de leitura com a unidade conforme o tipo da fonte
function Format-Valor {
    param([string]$Tipo, $Valor)
    $v = [math]::Round([double]$Valor, 1)
    switch ($Tipo) {
        'temperatura'  { "$v graus C" ; break }
        'qualidade_ar' { "$v ppm (CO2)" ; break }
        'camera'       { "$v pessoas" ; break }
        'semaforo'     { "estado $v" ; break }
        'poste'        { "nivel $v" ; break }
        default        { "$v" }
    }
}

# Converte timestamp UNIX em HH:mm:ss local
function Format-Hora {
    param($Ts)
    try { [DateTimeOffset]::FromUnixTimeSeconds([long]$Ts).LocalDateTime.ToString('HH:mm:ss') }
    catch { '--:--:--' }
}

# ═════════════════════════════════════════════════════════════════════════════
#  ACOES — SISTEMA
# ═════════════════════════════════════════════════════════════════════════════

function Start-Gateway {
    param($Status)
    if ($Status.Online) { return }   # ja rodando -> volta direto ao menu
    Write-Host ''
    Write-Host '   Iniciando Gateway no WSL (aguarde alguns segundos)...' -ForegroundColor Yellow
    $inner = "cd '$GwDirWsl' && '$GwPyWsl' gateway.py; echo; echo '[Gateway encerrado]'; exec bash"
    Start-Process 'wsl.exe' -ArgumentList "bash -c `"$inner`""
    # Aguarda ficar online para o menu ja redesenhar como ONLINE (sem pedir ENTER)
    for ($i = 0; $i -lt 14; $i++) {
        Start-Sleep -Milliseconds 500
        if ((Get-Status).Online) { break }
    }
}

function Connect-Fontes {
    Write-Host ''
    Write-Host '   Subindo as 5 fontes no WSL (aguarde o registro)...' -ForegroundColor Yellow
    $inner = "cd '$DemoWsl' && chmod +x demo_fontes.sh && ./demo_fontes.sh 127.0.0.1"
    Start-Process 'wsl.exe' -ArgumentList "bash -c `"$inner`""
    Start-Sleep -Seconds 4   # tempo das fontes se registrarem no Gateway
}

function Open-Dashboard {
    Write-Host ''
    Write-Host '   Abrindo o dashboard no navegador...' -ForegroundColor Yellow
    Start-Process $Dash
    Start-Sleep -Milliseconds 600
}

# ═════════════════════════════════════════════════════════════════════════════
#  ACOES — MONITORAR
# ═════════════════════════════════════════════════════════════════════════════

function Show-Fontes {
    param($Status)
    Show-Section 'Fontes Conectadas'
    if (-not (Require-Gateway $Status)) { return }
    try {
        $r = Get-Json '/fontes'
        if ($r.Count -eq 0) {
            Write-Host '   Nenhuma fonte registrada ainda.' -ForegroundColor Yellow
        } else {
            $r | Format-Table -AutoSize `
                @{L='ID';     E={$_.source_id}},
                @{L='Tipo';   E={$_.type}},
                @{L='Status'; E={$_.status}},
                @{L='Controlavel'; E={if ($_.controllable) {'sim'} else {'nao'}}},
                @{L='Conectado';   E={if ($_.conectado)    {'sim'} else {'nao'}}} | Out-Host
        }
    } catch { Write-Host '   Erro ao consultar a API.' -ForegroundColor Red }
    Pause-Menu
}

function Show-Alertas {
    param($Status)
    Show-Section 'Alertas Ativos'
    if (-not (Require-Gateway $Status)) { return }
    Write-Host '   Um ALERTA e uma leitura que passou do limite seguro' -ForegroundColor DarkGray
    Write-Host '   (ex: temperatura alta demais, CO2 acima do permitido).' -ForegroundColor DarkGray
    Write-Host ''
    try {
        $r = Get-Json '/alertas?segundos=3600&limite=20'
        if ($r.Count -eq 0) {
            Write-Host '   Tudo normal: nenhum alerta na ultima hora.' -ForegroundColor Green
        } else {
            Write-Host "   $($r.Count) leitura(s) em alerta na ultima hora:" -ForegroundColor Yellow
            Write-Host ''
            $r | Format-Table -AutoSize `
                @{L='Horario'; E={ Format-Hora $_.timestamp }},
                @{L='Fonte';   E={ $_.source_id }},
                @{L='Medicao'; E={ Format-Valor $_.type $_.valor }} | Out-Host
        }
    } catch { Write-Host '   Erro ao consultar a API.' -ForegroundColor Red }
    Pause-Menu
}

function Show-Estatisticas {
    param($Status)
    Show-Section 'Estatisticas do Sistema'
    if (-not (Require-Gateway $Status)) { return }

    # Media de temperatura (1h)
    Write-Host '   Temperatura media (ultima 1h):' -ForegroundColor White
    try {
        $m = Invoke-RestMethod "$Api/consultas/media?type=temperatura&segundos=3600"
        if ($null -eq $m.media) { Write-Host '      sem dados ainda' -ForegroundColor DarkGray }
        else { Write-Host "      $($m.media) graus C" -ForegroundColor Cyan }
    } catch { Write-Host '      erro' -ForegroundColor Red }

    # Desvio padrao CO2 (24h)
    Write-Host ''
    Write-Host '   Variacao do CO2 - desvio padrao (ultimas 24h):' -ForegroundColor White
    try {
        $d = Invoke-RestMethod "$Api/consultas/desvio?type=qualidade_ar&segundos=86400"
        if ($null -eq $d.desvio_padrao) { Write-Host '      sem dados ainda' -ForegroundColor DarkGray }
        else { Write-Host "      $($d.desvio_padrao) ppm" -ForegroundColor Cyan }
    } catch { Write-Host '      erro' -ForegroundColor Red }

    # Fonte com maior variacao
    Write-Host ''
    Write-Host '   Fonte mais instavel (maior variacao na ultima 1h):' -ForegroundColor White
    try {
        $v = Invoke-RestMethod "$Api/consultas/maior_variacao"
        if ($v) {
            $v.PSObject.Properties | ForEach-Object {
                Write-Host ("      {0}: {1}" -f $_.Name, $_.Value) -ForegroundColor Cyan
            }
        } else { Write-Host '      sem dados ainda' -ForegroundColor DarkGray }
    } catch { Write-Host '      erro' -ForegroundColor Red }

    Pause-Menu
}

# ═════════════════════════════════════════════════════════════════════════════
#  ACOES — CONTROLAR
# ═════════════════════════════════════════════════════════════════════════════

function Send-Comando {
    param([string]$Sid, [string]$Acao)
    try {
        $body = @{ source_id = $Sid; acao = $Acao; valor = 0 } | ConvertTo-Json -Compress
        $r = Invoke-RestMethod -Method Post -Uri "$Api/comando" -ContentType 'application/json' -Body $body
        $color = if ($r.sucesso) { 'Green' } else { 'Red' }
        Write-Host "   $($r.mensagem)" -ForegroundColor $color
    } catch { Write-Host '   Erro ao enviar comando (Gateway offline?).' -ForegroundColor Red }
}

function Control-Fonte {
    param($Status, [string]$Titulo, [string]$Acao)
    Show-Section $Titulo
    if (-not (Require-Gateway $Status)) { return }

    try { $fontes = Get-Json '/fontes' } catch { $fontes = @() }
    if ($fontes.Count -eq 0) {
        Write-Host '   Nenhuma fonte conectada.' -ForegroundColor Yellow
        Pause-Menu; return
    }

    Write-Host '   Escolha a fonte:' -ForegroundColor White
    Write-Host ''
    for ($i = 0; $i -lt $fontes.Count; $i++) {
        $f = $fontes[$i]
        if ($f.controllable) {
            Write-Host ("     {0}   {1,-14}({2})" -f ($i + 1), $f.source_id, $f.status)
        } else {
            Write-Host ("     {0}   {1,-14}" -f ($i + 1), $f.source_id) -NoNewline -ForegroundColor DarkGray
            Write-Host '(sensor - nao pode desativar)' -ForegroundColor DarkGray
        }
    }
    Write-Host ''
    $sel = Read-Host '   Numero da fonte (ENTER cancela)'
    if (-not $sel) { return }
    $idx = 0
    if (-not [int]::TryParse($sel, [ref]$idx) -or $idx -lt 1 -or $idx -gt $fontes.Count) {
        Write-Host '   Numero invalido.' -ForegroundColor Red; Pause-Menu; return
    }

    $alvo = $fontes[$idx - 1]
    if (-not $alvo.controllable) {
        Write-Host ''
        Write-Host "   $($alvo.source_id) e um sensor (UDP) e nao pode ser ativado/desativado." -ForegroundColor Yellow
        Write-Host '   Apenas atuadores (camera, semaforo, poste) sao controlaveis.' -ForegroundColor DarkGray
        Pause-Menu; return
    }

    $sid = $alvo.source_id
    Write-Host ''
    Send-Comando -Sid $sid -Acao $Acao
    if ($Acao -eq 'desativar') {
        Write-Host '   (use [4] Listar Fontes: o status vai aparecer como "inativo")' -ForegroundColor DarkGray
    }
    Pause-Menu
}

# ═════════════════════════════════════════════════════════════════════════════
#  ACOES — FALHAS
# ═════════════════════════════════════════════════════════════════════════════

function Kill-Fonte {
    param([string]$Sid)
    $bin = if ($BinMap.ContainsKey($Sid)) { $BinMap[$Sid] } else { $Sid }
    Write-Host "   Buscando processo de '$bin' no WSL..." -ForegroundColor White
    $procPid = @(wsl pgrep -x $bin)[0]
    if (-not $procPid) {
        Write-Host '   Processo nao encontrado automaticamente.' -ForegroundColor Yellow
        $procPid = Read-Host '   Digite o PID manualmente (veja na janela WSL)'
    }
    if (-not $procPid) { return $null }
    wsl kill $procPid
    Write-Host "   Processo $procPid derrubado  ($Sid)" -ForegroundColor Red
    return $procPid
}

function Simular-Falha {
    param($Status)
    Show-Section 'Derrubar uma Fonte (Simular Falha)'
    if (-not (Require-Gateway $Status)) { return }

    try { $fontes = Get-Json '/fontes' } catch { $fontes = @() }
    if ($fontes.Count -eq 0) {
        Write-Host '   Nenhuma fonte conectada. Use [2] Conectar Fontes antes.' -ForegroundColor Yellow
        Pause-Menu; return
    }

    Write-Host '   Escolha a fonte para derrubar:' -ForegroundColor White
    Write-Host ''
    for ($i = 0; $i -lt $fontes.Count; $i++) {
        Write-Host ("     {0}   {1}" -f ($i + 1), $fontes[$i].source_id)
    }
    Write-Host ''
    $sel = Read-Host '   Numero da fonte (ENTER cancela)'
    if (-not $sel) { return }
    $idx = 0
    if (-not [int]::TryParse($sel, [ref]$idx) -or $idx -lt 1 -or $idx -gt $fontes.Count) {
        Write-Host '   Numero invalido.' -ForegroundColor Red; Pause-Menu; return
    }

    $sid = $fontes[$idx - 1].source_id
    Write-Host ''
    if (Kill-Fonte $sid) {
        Write-Host ''
        Write-Host "   Fonte $sid derrubada." -ForegroundColor Green
    }
    Pause-Menu
}

function Stop-All {
    Show-Section 'Encerrar Sistema'
    Write-Host '   Encerrando fontes C no WSL...' -ForegroundColor White
    foreach ($p in 'sensor_temperatura','sensor_qualidade_ar','camera','semaforo','poste') {
        wsl pkill -x $p 2>$null
    }
    Write-Host '   Fontes encerradas.' -ForegroundColor Green
    Write-Host '   Encerrando Gateway no WSL...' -ForegroundColor White
    wsl pkill -f gateway.py 2>$null
    Write-Host '   Gateway encerrado.' -ForegroundColor Green
    Write-Host ''
    Write-Host '   Sistema encerrado. Bom video!' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '   Pressione ENTER para fechar o painel...' -ForegroundColor DarkGray
    [void](Read-Host)
}

# ═════════════════════════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════

function Show-Menu {
    param($Status)
    Clear-Host
    Write-Banner 'SmartCity · Painel de Controle'
    Write-Host ''
    if ($Status.Online) {
        Write-Host '   Gateway: ' -NoNewline
        Write-Host 'ONLINE' -NoNewline -ForegroundColor Green
        Write-Host '   ·   Fontes conectadas: ' -NoNewline
        Write-Host $Status.Count -ForegroundColor Cyan
    } else {
        Write-Host '   Gateway: ' -NoNewline
        Write-Host 'OFFLINE' -NoNewline -ForegroundColor Red
        Write-Host '   (comece pela opcao 1)' -ForegroundColor DarkGray
    }

    Write-Section 'PREPARAR'
    Write-Host '   [1] ' -NoNewline -ForegroundColor White; Write-Host 'Iniciar Gateway'
    Write-Host '   [2] ' -NoNewline -ForegroundColor White; Write-Host 'Conectar Fontes'
    Write-Host '   [3] ' -NoNewline -ForegroundColor White; Write-Host 'Abrir Dashboard'

    Write-Section 'MONITORAR'
    Write-Host '   [4] ' -NoNewline -ForegroundColor White; Write-Host 'Listar Fontes'
    Write-Host '   [5] ' -NoNewline -ForegroundColor White; Write-Host 'Ver Alertas'
    Write-Host '   [6] ' -NoNewline -ForegroundColor White; Write-Host 'Estatisticas (media, variacao)'

    Write-Section 'CONTROLAR'
    Write-Host '   [7] ' -NoNewline -ForegroundColor White; Write-Host 'Ativar uma Fonte'
    Write-Host '   [8] ' -NoNewline -ForegroundColor White; Write-Host 'Desativar uma Fonte'

    Write-Section 'TESTAR FALHA'
    Write-Host '   [9] ' -NoNewline -ForegroundColor White; Write-Host 'Derrubar uma Fonte (e ver o efeito)'

    Write-Host ''
    Write-Host '   [0] ' -NoNewline -ForegroundColor DarkGray; Write-Host 'Encerrar Tudo' -ForegroundColor DarkGray
    Write-Host ''
    Write-Host ('  ' + ([string]([char]0x2550) * 52)) -ForegroundColor Cyan
    Write-Host ''
}

# ── Loop principal ───────────────────────────────────────────────────────────
while ($true) {
    $status = Get-Status
    Show-Menu $status
    $op = (Read-Host '   Opcao').Trim()

    switch ($op) {
        '1' { Start-Gateway  $status }
        '2' { Connect-Fontes }
        '3' { Open-Dashboard }
        '4' { Show-Fontes       $status }
        '5' { Show-Alertas      $status }
        '6' { Show-Estatisticas $status }
        '7' { Control-Fonte $status 'Ativar uma Fonte'    'ativar' }
        '8' { Control-Fonte $status 'Desativar uma Fonte' 'desativar' }
        '9' { Simular-Falha $status }
        '0' { Stop-All; break }
        default {
            Write-Host '   Opcao invalida.' -ForegroundColor Red
            Start-Sleep -Milliseconds 800
        }
    }
    if ($op -eq '0') { break }
}
