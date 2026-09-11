# scripts/testar_instalador.ps1
# Teste automatizado do instalador Inno Setup do VersionFile.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\testar_instalador.ps1
#
# Pre-requisitos:
#   - Instalador compilado pelo Inno Setup em dist\ (VersionFile-*.exe)
#   - Nenhuma instancia do VersionFile rodando

param([switch]$ConfirmarAmbienteReal)

if (-not $ConfirmarAmbienteReal) {
    Write-Host "Este teste instala e desinstala o VersionFile no usuario atual."
    Write-Host "Execute novamente com -ConfirmarAmbienteReal em um usuario ou VM de teste."
    exit 2
}

$ErrorActionPreference = "Stop"

# Verifica que NAO esta rodando como admin — senao o teste de "sem UAC"
# nao prova nada (um instalador que exigisse admin passaria do mesmo jeito).
$souAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($souAdmin) {
    Write-Host "FALHOU: este script precisa rodar em PowerShell NAO elevado." -ForegroundColor Red
    Write-Host "Rodando como admin, o teste de 'sem UAC' nao prova nada." -ForegroundColor Red
    exit 1
}

$dataDir    = "$env:LOCALAPPDATA\VersionFile"
$installDir = "$env:LOCALAPPDATA\Programs\VersionFile"
$dbPath     = "$dataDir\versionfile.db"
$startMenu  = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\VersionFile"

# Detecta o instalador automaticamente (primeiro .exe em dist/ que nao seja o app)
$setupExe = Get-ChildItem -Path ".\dist" -Filter "VersionFile-*.exe" -File |
    Select-Object -First 1 | ForEach-Object { $_.FullName }

if (-not $setupExe) {
    Write-Host "  FALHOU: Nenhum instalador VersionFile-*.exe encontrado em dist\" -ForegroundColor Red
    Write-Host "  Compile com: ISCC installer\VersionFile.iss /DAppVersion=1.2.0-teste"
    exit 1
}
Write-Host "  Instalador detectado: $setupExe"

$falhas = 0

function Resultado($nome, $passou) {
    if ($passou) {
        Write-Host "  PASS: $nome" -ForegroundColor Green
    } else {
        Write-Host "  FALHOU: $nome" -ForegroundColor Red
        $script:falhas++
    }
}

# ============================================================
Write-Host "`n=============================="
Write-Host "  FASE 1: Pre-instalacao"
Write-Host "==============================`n"

# Garante que a pasta de dados existe
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Write-Host "  Pasta de dados criada: $dataDir"
}

# Banco sintetico de teste (se nao existir um real)
$dbCriado = $false
if (-not (Test-Path $dbPath)) {
    # Cria um banco SQLite minimo sintetico (so o header basta para o teste de hash)
    # Os primeiros 16 bytes de um SQLite sao "SQLite format 3\0"
    # Vamos usar Python para criar um banco valido minimo
    py -3.11 -c "import sqlite3; c=sqlite3.connect(r'$dbPath'); c.execute('CREATE TABLE teste(id INTEGER)'); c.close()"
    $dbCriado = $true
    Write-Host "  Banco sintetico criado: $dbPath"
} else {
    Write-Host "  Banco existente encontrado: $dbPath"
    Write-Host "  ATENCAO: usando banco real - o teste NAO vai modifica-lo"
}

# Hash SHA256 do banco antes
$hashAntes = (Get-FileHash -Path $dbPath -Algorithm SHA256).Hash
Write-Host "  SHA256 do banco (antes): $hashAntes"

# Snapshot dos arquivos na pasta de dados
$snapshotAntes = Get-ChildItem -Path $dataDir -Recurse -File | ForEach-Object {
    [PSCustomObject]@{
        RelPath      = $_.FullName.Substring($dataDir.Length)
        LastWrite    = $_.LastWriteTimeUtc.ToString("o")
        Size         = $_.Length
    }
}
Write-Host "  Arquivos na pasta de dados (antes): $($snapshotAntes.Count)"
foreach ($f in $snapshotAntes) {
    Write-Host "    $($f.RelPath)  ($($f.Size) bytes, $($f.LastWrite))"
}

# (instalador ja verificado no topo do script)

# ============================================================
Write-Host "`n=============================="
Write-Host "  FASE 2: Instalacao silenciosa"
Write-Host "==============================`n"

Write-Host "  Rodando: $setupExe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART"

$proc = Start-Process -FilePath $setupExe `
    -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" `
    -PassThru -Wait

Resultado "Instalador terminou sem erro (exit code: $($proc.ExitCode))" ($proc.ExitCode -eq 0)

# Pequena pausa para garantir que arquivos foram gravados
Start-Sleep -Seconds 2

# ============================================================
Write-Host "`n=============================="
Write-Host "  FASE 3: Verificacoes pos-instalacao"
Write-Host "==============================`n"

# 3.1 - Executavel instalado
$exeInstalado = Test-Path "$installDir\VersionFile.exe"
Resultado "VersionFile.exe existe em $installDir" $exeInstalado

# 3.2 - Hash do banco inalterado
$hashDepois = (Get-FileHash -Path $dbPath -Algorithm SHA256).Hash
Write-Host "  SHA256 do banco (depois): $hashDepois"
Resultado "Hash do banco inalterado apos instalacao" ($hashAntes -eq $hashDepois)

# 3.3 - Nenhum arquivo novo na pasta de dados
$snapshotDepois = Get-ChildItem -Path $dataDir -Recurse -File | ForEach-Object {
    [PSCustomObject]@{
        RelPath      = $_.FullName.Substring($dataDir.Length)
        LastWrite    = $_.LastWriteTimeUtc.ToString("o")
        Size         = $_.Length
    }
}

$novos = @()
foreach ($f in $snapshotDepois) {
    $existia = $snapshotAntes | Where-Object { $_.RelPath -eq $f.RelPath }
    if (-not $existia) {
        $novos += $f.RelPath
    }
}
if ($novos.Count -gt 0) {
    Write-Host "  Arquivos novos detectados:"
    foreach ($n in $novos) { Write-Host "    $n" -ForegroundColor Yellow }
}
Resultado "Nenhum arquivo novo em $dataDir" ($novos.Count -eq 0)

# 3.4 - Atalho no Menu Iniciar
$atalhoExiste = Test-Path "$startMenu\VersionFile.lnk"
Resultado "Atalho no Menu Iniciar criado" $atalhoExiste

# ============================================================
Write-Host "`n=============================="
Write-Host "  FASE 4: Execucao do app instalado"
Write-Host "==============================`n"

$appProc = Start-Process -FilePath "$installDir\VersionFile.exe" -PassThru
Start-Sleep -Seconds 5

$appRodando = -not $appProc.HasExited
Resultado "App iniciou e esta rodando apos 5s" $appRodando

if (-not $appProc.HasExited) {
    $appProc.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 2
    if (-not $appProc.HasExited) {
        $appProc.Kill()
    }
    Write-Host "  App fechado."
}

# ============================================================
Write-Host "`n=============================="
Write-Host "  FASE 5: Desinstalacao silenciosa"
Write-Host "==============================`n"

$uninstExe = "$installDir\unins000.exe"
if (Test-Path $uninstExe) {
    Write-Host "  Rodando: $uninstExe /VERYSILENT /SUPPRESSMSGBOXES"

    $unProc = Start-Process -FilePath $uninstExe `
        -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES" `
        -PassThru -Wait

    Resultado "Desinstalador terminou sem erro (exit code: $($unProc.ExitCode))" ($unProc.ExitCode -eq 0)

    # O Inno Setup spawna um processo filho para remover a pasta (o .exe roda
    # de dentro dela). Aguarda ate 15s pela remoção completa.
    $espera = 0
    while ((Test-Path $installDir) -and $espera -lt 15) {
        Start-Sleep -Seconds 1
        $espera++
    }
    Write-Host "  Aguardou ${espera}s pela limpeza do desinstalador."
} else {
    Write-Host "  FALHOU: unins000.exe nao encontrado em $installDir" -ForegroundColor Red
    $falhas++
}

# 5.1 - Pasta de instalacao removida
$installRemovido = -not (Test-Path $installDir)
Resultado "Pasta de instalacao removida ($installDir)" $installRemovido

# 5.2 - Hash do banco continua o mesmo (verificacao MAIS IMPORTANTE)
$hashFinal = (Get-FileHash -Path $dbPath -Algorithm SHA256).Hash
Write-Host "  SHA256 do banco (final): $hashFinal"
Resultado "Hash do banco intacto apos desinstalacao (CRITICO)" ($hashAntes -eq $hashFinal)

# ============================================================
Write-Host "`n=============================="
Write-Host "  RESUMO"
Write-Host "==============================`n"

if ($falhas -eq 0) {
    Write-Host "  Todos os testes passaram!" -ForegroundColor Green
} else {
    Write-Host "  $falhas teste(s) falharam." -ForegroundColor Red
}

# Limpeza: remove banco sintetico se foi criado por este script
if ($dbCriado -and (Test-Path $dbPath)) {
    Remove-Item $dbPath -Force
    Write-Host "`n  Banco sintetico de teste removido."
    # Remove pasta de dados se ficou vazia (so se foi criada por nos)
    $restantes = Get-ChildItem -Path $dataDir -Recurse -File
    if ($restantes.Count -eq 0) {
        Remove-Item $dataDir -Recurse -Force
        Write-Host "  Pasta de dados de teste removida."
    }
}

Write-Host ""
exit $falhas
