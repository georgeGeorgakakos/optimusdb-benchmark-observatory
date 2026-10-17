<#
.SYNOPSIS
  Publishes the results to GitHub: builds the dashboard snapshot (site\), commits results and snapshot, pushes.
  GitHub Actions then updates the published dashboard (GitHub Pages) within a minute or two.
.EXAMPLE
  .\publish-results.ps1                         # build, commit, push
  .\publish-results.ps1 -Message "quick run 8"
  .\publish-results.ps1 -NoPush                 # build and commit only (push later from PyCharm)
  .\publish-results.ps1 -BuildOnly              # only rebuild site\ (preview it locally first)
#>
param([string]$Message, [switch]$NoPush, [switch]$BuildOnly, [switch]$NoOps)
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'

# 1. build site\ : with the testbed's own Python image (nothing to install), or a local Python if Docker is off
Write-Step 'Building the dashboard snapshot (site\)'
$extra = @(); if ($NoOps) { $extra += '--no-ops' }
$null = Invoke-Native 'docker' @('image', 'inspect', 'odb-bench:latest')
if ($LASTEXITCODE -eq 0) {
    $out = Invoke-Native 'docker' (@('run', '--rm', '-v', "${Root}:/work", '-w', '/work', '--entrypoint', 'python', 'odb-bench:latest',
                                     'tools/build_site.py', '--results', 'results', '--archive', 'results-archive', '--out', 'site') + $extra) -Merge
} else {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $py) { Write-Fail 'Neither the odb-bench image nor Python was found. Run .\fresh-start.ps1 once, or install Python 3.'; exit 1 }
    $out = & $py.Source (Join-Path $Root 'tools\build_site.py') @extra 2>&1
}
$out | ForEach-Object { Write-Host "  $_" }
if (-not (Test-Path (Join-Path $Root 'site\site-data\manifest.json'))) { Write-Fail 'The snapshot was not built (see above).'; exit 1 }
Write-Ok 'site\ built. Preview: PyCharm run configuration "Preview site", then http://localhost:8600'
if ($BuildOnly) { return }

# 2. commit
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { Write-Fail 'git not found. Install Git for Windows (PyCharm uses it too).'; exit 1 }
Push-Location $Root
try {
    if (-not (Test-Path '.git')) { Write-Fail 'This folder is not a Git repository yet. See README-GITHUB.md, step 2.'; exit 1 }
    if (-not $Message) { $Message = "Results " + (Get-Date -Format 'yyyy-MM-dd HH:mm') }
    git add -A results results-archive site 2>&1 | Out-Null
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) { Write-Ok 'Nothing new to commit.' }
    else { git commit -m $Message | Select-Object -Last 2 | Out-Host; Write-Ok "Committed: $Message" }
    if ($NoPush) { Write-Ok 'Not pushed (-NoPush). Push from PyCharm (Git -> Push) when ready.'; return }
    Write-Step 'Pushing'
    git push 2>&1 | Select-Object -Last 3 | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Push failed (see above). Push from PyCharm instead, or check your GitHub login.'; exit 1 }
    $url = (git remote get-url origin) -replace '\.git$', ''
    if ($url -match 'github\.com[:/]([^/]+)/([^/]+)$') { Write-Ok ("Pushed. The dashboard updates in 1-2 minutes at https://{0}.github.io/{1}/  (progress: {2}/actions)" -f $Matches[1].ToLower(), $Matches[2], ($url -replace '^git@github\.com:', 'https://github.com/')) }
} finally { Pop-Location }
