# Shared helpers for the PowerShell scripts (Windows, Docker Desktop with the WSL2 backend).
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AllSystems = @('optimusdb', 'corrosion', 'gun', 'autobase', 'iroh', 'opendht')

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

function Invoke-Native {
    # Runs a native command so that its stderr can never become a terminating error. With $ErrorActionPreference
    # 'Stop', Windows PowerShell 5.1 turns any redirected stderr line of a native program into an exception.
    # Returns stdout (or stdout+stderr with -Merge); $LASTEXITCODE is set as usual.
    param([string]$Exe, [string[]]$Arguments, [switch]$Merge)
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
        if ($Merge) { & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } }
        else { & $Exe @Arguments 2>$null }
    } finally { $ErrorActionPreference = $old }
}

function Get-BenchState {
    # 'running', 'exited', ... or '' when the odb-bench container does not exist. --type container: an image
    # called odb-bench also exists, and plain `docker inspect` would match it.
    $s = Invoke-Native 'docker' @('inspect', '--type', 'container', '-f', '{{.State.Status}}', 'odb-bench')
    if ($LASTEXITCODE -ne 0) { return '' }
    return "$s".Trim()
}

function Assert-Docker {
    $null = Invoke-Native 'docker' @('version', '--format', '{{.Server.Os}}')
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running (docker version failed). Start Docker Desktop and retry.' }
    $os = (& docker version --format '{{.Server.Os}}').Trim()
    if ($os -ne 'linux') { throw "Docker Desktop must use Linux containers (current: $os). Right-click the tray icon > Switch to Linux containers." }
}

function Read-EnvFile([string]$Path) {
    $h = @{}
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $k, $v = $line -split '=', 2
        $h[$k.Trim()] = $v.Trim()
    }
    return $h
}

function Get-HostDir([string]$Name) {
    $d = Join-Path $Root "out\$Name"
    if (-not (Test-Path (Join-Path $d '.env'))) { throw "No bundle for '$Name' in $Root\out. Run gen-config.ps1 first and copy the out folder to this host." }
    return (Resolve-Path $d).Path
}

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

function Invoke-Compose {
    param([string]$File, [string]$EnvFile, [string[]]$Arguments)
    Invoke-Checked 'docker' (@('compose', '-f', (Join-Path $Root "compose\$File"), '--env-file', $EnvFile) + $Arguments)
}

function Invoke-Bench {
    # Runs a harness command inside the bench container (bench host only).
    param([string[]]$Arguments, [switch]$Detach)
    $state = Get-BenchState
    if ($state -ne 'running') {
        $null = Invoke-Native 'docker' @('info')
        if ($LASTEXITCODE -ne 0) { throw 'Docker is not running. Start Docker Desktop, wait until it shows "Engine running", then try again.' }
        if (-not $state) { throw 'The odb-bench container does not exist. Single machine: run .\deploy-local.ps1   Multi-host: run deploy-bench.ps1 on the bench host.' }
        throw "odb-bench is $state. Start it with: docker start odb-bench   (see why it stopped: docker logs --tail 50 odb-bench)"
    }
    $a = @('exec') + $(if ($Detach) { @('-d') } else { @() }) + @('odb-bench') + $Arguments
    Invoke-Checked 'docker' $a
}

function Resolve-OptimusSource([string]$Src) {
    # A git URL with #ref is cloned into .src\optimusdb with git running in a container (no git needed on
    # Windows) and built from there. Building straight from the URL fails because the repository contains a
    # submodule entry (binding/go-llama.cpp) without a .gitmodules URL, which Docker's git loader cannot fetch.
    # The ref may be a commit hash (recommended for the paper: reproducible) or a branch name such as main
    # (always builds the latest pushed commit of that branch). The code is built exactly as it is in the repository.
    if ($Src -notmatch '^(https?://[^#]+)#(.+)$') { return $Src }
    $url = $Matches[1]; $ref = $Matches[2]
    $srcRoot = Join-Path $Root '.src'
    New-Item -ItemType Directory -Force -Path $srcRoot | Out-Null
    $git = @('run', '--rm', '-v', "${srcRoot}:/src", 'alpine/git:latest', '-c', 'safe.directory=*')
    if (-not (Test-Path (Join-Path $srcRoot 'optimusdb\.git'))) {
        Write-Step "Cloning $url"
        Invoke-Checked 'docker' ($git + @('clone', '--no-checkout', $url, '/src/optimusdb')) | Out-Host
    }
    # A branch name is checked out from the freshly fetched origin copy, so a new push is always picked up.
    $target = if ($ref -match '^[0-9a-fA-F]{7,40}$') { $ref } else { "origin/$ref" }
    Write-Step "Checking out $ref"
    Invoke-Checked 'docker' ($git + @('-C', '/src/optimusdb', 'fetch', 'origin')) | Out-Host
    Invoke-Checked 'docker' ($git + @('-C', '/src/optimusdb', 'checkout', '-f', '--detach', $target)) | Out-Host
    Invoke-Checked 'docker' ($git + @('-C', '/src/optimusdb', 'clean', '-fdq')) | Out-Host
    $head = (Invoke-Native 'docker' ($git + @('-C', '/src/optimusdb', 'log', '-1', '--format=%H %s')) | Select-Object -First 1)
    Write-Ok "OptimusDB source: $head"
    $co = Join-Path $srcRoot 'optimusdb'
    if ((Test-Path (Join-Path $co 'app\batch_put.go')) -and (Test-Path (Join-Path $co 'third_party\go-orbit-db\go.mod'))) {
        Write-Ok 'Batched ingestion code found (app\batch_put.go, third_party\go-orbit-db)'
    } else {
        Write-Warn2 'This commit does NOT contain the batched ingestion code (app\batch_put.go, third_party\go-orbit-db).'
        Write-Warn2 'OptimusDB will load one document at a time. Push the changed code and set OPTIMUSDB_SRC in versions.env.'
    }
    if ((Test-Path (Join-Path $co 'app\group_commit.go')) -and (Test-Path (Join-Path $co 'app\lineage_queue.go'))) {
        Write-Ok 'Performance code found (group commit, field indexes, document cache)'
    } else {
        Write-Warn2 'This commit does NOT contain the performance changes (app\group_commit.go). Push them before measuring.'
    }
    return $co
}
