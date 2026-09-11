# scripts/capturar_processos.ps1
# Captura arvore de processos VersionFile e Setup via polling rapido.
# Nao precisa de admin.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\capturar_processos.ps1

param(
    [switch]$ConfirmarAmbienteReal,
    [string]$VersaoAntiga = "1.1.0"
)

if (-not $ConfirmarAmbienteReal) {
    Write-Host "Este diagnostico instala versões e encerra processos do VersionFile."
    Write-Host "Execute novamente com -ConfirmarAmbienteReal em um usuario ou VM de teste."
    exit 2
}

$ErrorActionPreference = "Stop"

$installDir  = "$env:LOCALAPPDATA\Programs\VersionFile"
$setupAntigo = ".\dist\VersionFile-$VersaoAntiga-Setup.exe"
$cacheUpdate = "$env:LOCALAPPDATA\VersionFile\config\update_check.json"
$bootLog     = "$env:LOCALAPPDATA\VersionFile\boot.log"

if (-not (Test-Path $setupAntigo)) {
    Write-Host "ERRO: $setupAntigo nao encontrado." -ForegroundColor Red
    exit 1
}

# -- Matar qualquer VersionFile residual ----------------------------------
Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue | ForEach-Object {
    $_.Kill()
}
Start-Sleep -Seconds 1

# -- Limpar boot.log ------------------------------------------------------
if (Test-Path $bootLog) { Remove-Item $bootLog -Force }

# Remover cache de update antecipadamente
if (Test-Path $cacheUpdate) {
    Remove-Item $cacheUpdate -Force
}

# -- Funcao de log com timestamp ------------------------------------------
function Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss.fff"
    Write-Host "[$ts] $msg"
}

# -- Rastreamento de processos via polling --------------------------------
$processosConhecidos = @{}
$eventosLog = [System.Collections.ArrayList]::new()

function Checar-Processos {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "VersionFile|Setup" }

    $atuais = @{}
    foreach ($p in $procs) {
        $atuais[$p.ProcessId] = $p
    }

    # Detectar novos
    foreach ($procId in $atuais.Keys) {
        if (-not $processosConhecidos.ContainsKey($procId)) {
            $p = $atuais[$procId]

            # Nome do processo pai
            $parentName = ""
            try {
                $pp = Get-CimInstance Win32_Process -Filter "ProcessId = $($p.ParentProcessId)" -ErrorAction SilentlyContinue
                if ($pp) { $parentName = $pp.Name }
            } catch {}

            $info = [PSCustomObject]@{
                PID        = $procId
                ParentPID  = $p.ParentProcessId
                ParentName = $parentName
                Nome       = $p.Name
                CmdLine    = $p.CommandLine
                HoraInicio = Get-Date
            }
            $processosConhecidos[$procId] = $info
            [void]$eventosLog.Add([PSCustomObject]@{
                Timestamp = (Get-Date -Format "HH:mm:ss.fff")
                Tipo = "START"
                Info = $info
            })
            Log "START: PID=$procId  ParentPID=$($p.ParentProcessId) ($parentName)  Nome=$($p.Name)"
            if ($p.CommandLine) {
                Log "       CmdLine: $($p.CommandLine)"
            }
        }
    }

    # Detectar encerrados
    $encerrados = @($processosConhecidos.Keys | Where-Object { -not $atuais.ContainsKey($_) })
    foreach ($procId in $encerrados) {
        $info = $processosConhecidos[$procId]
        $duracao = [math]::Round(((Get-Date) - $info.HoraInicio).TotalSeconds, 1)
        [void]$eventosLog.Add([PSCustomObject]@{
            Timestamp = (Get-Date -Format "HH:mm:ss.fff")
            Tipo = "STOP"
            Info = $info
            Duracao = $duracao
        })
        Log "STOP:  PID=$procId  Nome=$($info.Nome)  Durou=${duracao}s"
        $processosConhecidos.Remove($procId)
    }
}

# -- Lançar instalador anterior sem -Wait e observar em paralelo ----------
Log "Lancando instalador v$VersaoAntiga (sem -Wait, polling em paralelo)..."
$setupProc = Start-Process -FilePath $setupAntigo `
    -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" `
    -PassThru

Log ""
Log "=== CAPTURANDO PROCESSOS (polling 150ms, 120s max) ==="
Log ""

$inicio = Get-Date
$duracaoMax = 120
$setupTerminou = $false

while (((Get-Date) - $inicio).TotalSeconds -lt $duracaoMax) {
    Checar-Processos

    # Marca quando o instalador anterior termina
    if (-not $setupTerminou -and $setupProc.HasExited) {
        $setupTerminou = $true
        Log "--- Instalador v$VersaoAntiga (PID=$($setupProc.Id)) terminou (exit=$($setupProc.ExitCode)) ---"
    }

    # Condição de parada: instalador anterior terminou e nenhum processo
    # VersionFile/Setup esta rodando E ja se passaram pelo menos 30s
    if ($setupTerminou -and
        $processosConhecidos.Count -eq 0 -and
        ((Get-Date) - $inicio).TotalSeconds -gt 30) {
        # Espera mais 10s para garantir que nada novo surge
        $esperaExtra = 0
        $algoSurgiu = $false
        while ($esperaExtra -lt 10) {
            Start-Sleep -Milliseconds 500
            $esperaExtra += 0.5
            Checar-Processos
            if ($processosConhecidos.Count -gt 0) {
                $algoSurgiu = $true
                break
            }
        }
        if (-not $algoSurgiu) {
            Log "--- Nenhum processo ativo apos 10s de silencio. Parando. ---"
            break
        }
    }

    Start-Sleep -Milliseconds 150
}

# Checagem final
Checar-Processos

# -- Resumo ---------------------------------------------------------------
Log ""
Log "=========================================="
Log "  RESUMO: ARVORE DE PROCESSOS"
Log "=========================================="
Log ""

foreach ($e in $eventosLog) {
    $i = $e.Info
    if ($e.Tipo -eq "START") {
        Log "$($e.Timestamp) START PID=$($i.PID)  ParentPID=$($i.ParentPID) ($($i.ParentName))  $($i.Nome)"
        if ($i.CmdLine) {
            Log "                           CmdLine: $($i.CmdLine)"
        }
    } else {
        Log "$($e.Timestamp) STOP  PID=$($i.PID)  $($i.Nome)  (durou $($e.Duracao)s)"
    }
}

# -- boot.log -------------------------------------------------------------
Log ""
Log "=========================================="
Log "  CONTEUDO DO boot.log"
Log "=========================================="
Log ""
if (Test-Path $bootLog) {
    Get-Content $bootLog | ForEach-Object { Log "  $_" }
} else {
    Log "(boot.log nao existe)"
}

# -- Matar processos residuais -------------------------------------------
Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue | ForEach-Object {
    $_.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 2
    if (-not $_.HasExited) { $_.Kill() }
}
Log ""
Log "Concluido."
