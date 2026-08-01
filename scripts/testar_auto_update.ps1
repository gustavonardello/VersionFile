# scripts/testar_auto_update.ps1
# Teste do ciclo completo de auto-update (5 rodadas).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\testar_auto_update.ps1
#
# Pre-requisitos:
#   - dist\VersionFile-1.0.0-Setup.exe (versao antiga, para instalar)
#   - Release v1.1.0 publicada no GitHub com asset Setup.exe
#   - Nenhuma instancia do VersionFile rodando

$ErrorActionPreference = "Stop"

# Guarda contra admin
$souAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($souAdmin) {
    Write-Host "FALHOU: rode em PowerShell NAO elevado." -ForegroundColor Red
    exit 1
}

$dataDir       = "$env:LOCALAPPDATA\VersionFile"
$installDir    = "$env:LOCALAPPDATA\Programs\VersionFile"
$dbPath        = "$dataDir\versionfile.db"
$setupAntigo   = ".\dist\VersionFile-1.0.0-Setup.exe"
$cacheUpdate   = "$dataDir\config\update_check.json"
$rodadas       = 5
$falhasTotais  = 0

if (-not (Test-Path $setupAntigo)) {
    Write-Host "FALHOU: $setupAntigo nao encontrado." -ForegroundColor Red
    exit 1
}

# Hash inicial do banco
if (Test-Path $dbPath) {
    $hashInicial = (Get-FileHash -Path $dbPath -Algorithm SHA256).Hash
    Write-Host "Hash SHA256 do banco (inicio): $hashInicial"
} else {
    Write-Host "Banco nao existe ainda - sera criado na primeira execucao."
    $hashInicial = $null
}

function Matar-VersionFile {
    Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue | ForEach-Object {
        $_.CloseMainWindow() | Out-Null
        Start-Sleep -Seconds 2
        if (-not $_.HasExited) { $_.Kill() }
    }
    Start-Sleep -Seconds 1
}

function Resultado($nome, $passou) {
    if ($passou) {
        Write-Host "    PASS: $nome" -ForegroundColor Green
    } else {
        Write-Host "    FALHOU: $nome" -ForegroundColor Red
        $script:falhasTotais++
    }
}

for ($i = 1; $i -le $rodadas; $i++) {
    Write-Host "`n$('='*60)"
    Write-Host "  RODADA $i de $rodadas"
    Write-Host "$('='*60)`n"

    # -- Garantir que nenhum VersionFile esta rodando ---------------------
    Matar-VersionFile

    # -- Instalar versao antiga (1.0.0) -----------------------------------
    Write-Host "  Instalando v1.0.0..."
    $proc = Start-Process -FilePath $setupAntigo `
        -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" `
        -PassThru -Wait
    Resultado "Instalacao v1.0.0 (exit code: $($proc.ExitCode))" ($proc.ExitCode -eq 0)
    Start-Sleep -Seconds 2

    # Confirma que a versao instalada e 1.0.0
    $exeInstalado = Test-Path "$installDir\VersionFile.exe"
    Resultado "VersionFile.exe instalado" $exeInstalado

    # -- Remover cache de update para forcar checagem ---------------------
    if (Test-Path $cacheUpdate) {
        Remove-Item $cacheUpdate -Force
        Write-Host "  Cache de update removido (forcar checagem)."
    }

    # -- Esperar o app v1.0.0 que o [Run] do instalador ja abriu ---------
    # O instalador com /VERYSILENT executa a entrada [Run] automaticamente,
    # entao o app ja deve estar rodando. Detectamos o processo em vez de
    # abrir uma segunda instancia manualmente.
    Write-Host "  Aguardando VersionFile v1.0.0 surgir (aberto pelo instalador)..."
    $esperouSurgir = 0
    $surgirTimeout = 15
    $appProc = $null

    while ($esperouSurgir -lt $surgirTimeout) {
        Start-Sleep -Seconds 1
        $esperouSurgir++
        $appProc = Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($appProc) {
            Write-Host "  VersionFile v1.0.0 detectado (PID=$($appProc.Id)) apos ${esperouSurgir}s."
            break
        }
    }

    if (-not $appProc) {
        Write-Host "    FALHOU: VersionFile v1.0.0 nao surgiu em ${surgirTimeout}s." -ForegroundColor Red
        $falhasTotais++
        continue
    }

    # Aguarda ate 120s para o processo v1.0.0 morrer (auto-update detecta
    # v1.1.0, baixa, lanca instalador e faz self.close()).
    Write-Host "  Aguardando auto-update (processo v1.0.0 deve fechar)..."
    $timeout = 120
    $esperou = 0
    $processoOriginalMorreu = $false

    while ($esperou -lt $timeout) {
        Start-Sleep -Seconds 2
        $esperou += 2

        if ($appProc.HasExited) {
            $processoOriginalMorreu = $true
            Write-Host "  Processo original (v1.0.0) terminou apos ${esperou}s."
            break
        }
    }

    if (-not $processoOriginalMorreu) {
        Write-Host "    FALHOU: app v1.0.0 nao fechou em ${timeout}s." -ForegroundColor Red
        $falhasTotais++
        Matar-VersionFile
        continue
    }

    # Aguarda o instalador terminar e o app novo abrir
    Write-Host "  Aguardando instalador terminar e app v1.1.0 reabrir..."
    $esperouReabrir = 0
    $reabrirTimeout = 30
    $novoProcesso = $null

    while ($esperouReabrir -lt $reabrirTimeout) {
        Start-Sleep -Seconds 2
        $esperouReabrir += 2
        $novoProcesso = Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($novoProcesso) {
            Write-Host "  App reabriu apos ${esperouReabrir}s."
            break
        }
    }

    Resultado "App reabriu automaticamente" ($null -ne $novoProcesso)

    if ($novoProcesso) {
        # Espera o app estabilizar e verifica instancias
        Start-Sleep -Seconds 5
        $todosProcessos = @(Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue)

        # Se nao ha nenhum processo, pode ser que o app ainda nao subiu
        # (o [Run] pode demorar). Aguarda mais um pouco e tenta de novo.
        if ($todosProcessos.Count -eq 0) {
            Write-Host "    Nenhuma instancia detectada apos 5s, aguardando mais 5s..."
            Start-Sleep -Seconds 5
            $todosProcessos = @(Get-Process -Name "VersionFile" -ErrorAction SilentlyContinue)
        }

        Write-Host "    Instancias rodando: $($todosProcessos.Count)"
        Resultado "Exatamente 1 instancia rodando (nao duplicada)" ($todosProcessos.Count -eq 1)

        # Reatribui para usar nos passos seguintes (fechar, etc.)
        if ($todosProcessos.Count -ge 1) {
            $novoProcesso = $todosProcessos[0]
        }

        # Verifica a versao lendo o AppVersion do registro do Inno Setup
        $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1"
        $regVer = $null
        if (Test-Path $regPath) {
            $regVer = (Get-ItemProperty -Path $regPath -Name "DisplayVersion" -ErrorAction SilentlyContinue).DisplayVersion
        }
        if ($regVer) {
            Write-Host "    Versao instalada (registro): $regVer"
            Resultado "Versao e 1.1.0 (nao 1.0.0)" ($regVer -eq "1.1.0")
        } else {
            Write-Host "    AVISO: nao foi possivel ler versao do registro" -ForegroundColor Yellow
        }

        # Fecha o app
        $novoProcesso.CloseMainWindow() | Out-Null
        Start-Sleep -Seconds 2
        if (-not $novoProcesso.HasExited) {
            $novoProcesso.Kill()
        }
        Write-Host "  App fechado."
    }

    # -- Verifica integridade do banco ------------------------------------
    if (Test-Path $dbPath) {
        $hashAtual = (Get-FileHash -Path $dbPath -Algorithm SHA256).Hash
        if ($hashInicial) {
            Resultado "Hash do banco intacto (rodada $i)" ($hashInicial -eq $hashAtual)
        } else {
            # Primeira rodada criou o banco - salva hash para proximas
            $hashInicial = $hashAtual
            Write-Host "    Hash do banco registrado: $hashInicial"
        }
    } else {
        Write-Host "    AVISO: banco nao existe" -ForegroundColor Yellow
    }
}

# ============================================================
Write-Host "`n$('='*60)"
Write-Host "  RESUMO FINAL (${rodadas} rodadas)"
Write-Host "$('='*60)`n"

# Verificacao final do banco
if ($hashInicial -and (Test-Path $dbPath)) {
    $hashFinal = (Get-FileHash -Path $dbPath -Algorithm SHA256).Hash
    Resultado "Hash do banco intacto apos TODAS as rodadas (CRITICO)" ($hashInicial -eq $hashFinal)
}

if ($falhasTotais -eq 0) {
    Write-Host "`n  Todas as $rodadas rodadas passaram!" -ForegroundColor Green
} else {
    Write-Host "`n  $falhasTotais falha(s) no total." -ForegroundColor Red
}

# Limpeza: desinstala a versao que ficou
$uninstExe = "$installDir\unins000.exe"
if (Test-Path $uninstExe) {
    Write-Host "`n  Desinstalando versao final de teste..."
    $unProc = Start-Process -FilePath $uninstExe `
        -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES" `
        -PassThru -Wait
    $espera = 0
    while ((Test-Path $installDir) -and $espera -lt 15) {
        Start-Sleep -Seconds 1
        $espera++
    }
    Write-Host "  Desinstalado."
}

Write-Host ""
exit $falhasTotais
