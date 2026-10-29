param([string]$Message)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.conda-env\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run setup.bat first; no global Python fallback.' }
& $projectPython (Join-Path $PSScriptRoot 'verify_env.py')
if ($LASTEXITCODE -ne 0) { throw 'Project interpreter validation failed.' }
$branch = & git branch --show-current
if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'This shortcut only updates main. Review other branches manually.' }
$remote = & git remote get-url origin
if ($LASTEXITCODE -ne 0 -or $remote -notin @('https://github.com/shipshipliucixin1/innovation-dance.git', 'https://github.com/shipshipliucixin1/innovation-dance', 'git@github.com:shipshipliucixin1/innovation-dance.git')) {
    throw 'Unexpected origin. Review the destination before publishing.'
}
# No proxy or global Git settings are changed. Optional direct connection is
# explicitly selected by setting PROJECTFLOW_GIT_DIRECT=1 for this process.
$gitOptions = @()
if ($env:PROJECTFLOW_GIT_DIRECT -eq '1') { $gitOptions = @('-c', 'http.proxy=') }
& git @gitOptions fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed. Check GitHub login/network. No commit or push was attempted.' }
& git show-ref --verify --quiet refs/remotes/origin/main
if ($LASTEXITCODE -eq 0) {
    & git merge-base --is-ancestor origin/main HEAD
    if ($LASTEXITCODE -ne 0) {
        throw 'Remote main has changes not in this checkout. Integrate them safely, then rerun. No history was overwritten.'
    }
}
& $projectPython (Join-Path $PSScriptRoot 'check_secrets.py')
if ($LASTEXITCODE -ne 0) { throw 'Safety check failed. Do not push until the reported risk is resolved.' }
& git add --all
if ($LASTEXITCODE -ne 0) { throw 'Staging failed.' }
& $projectPython (Join-Path $PSScriptRoot 'check_secrets.py') --staged-only
if ($LASTEXITCODE -ne 0) { throw 'Staged/history safety check failed. No commit or push was attempted.' }
& git diff --cached --quiet
$diffStatus = $LASTEXITCODE
if ($diffStatus -eq 1) {
    & git diff --cached --stat
    if (-not $Message) { $Message = Read-Host 'Describe this update (Enter for Update ProjectFlow)' }
    if (-not $Message) { $Message = 'Update ProjectFlow' }
    & git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw 'Commit failed; staged changes are preserved.' }
} elseif ($diffStatus -ne 0) {
    throw 'Unable to inspect staged changes.'
} else {
    Write-Host 'No new working changes. Checking for an existing local commit to push.'
}
& git @gitOptions push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed. The local commit is preserved; resolve login/network/remote updates and retry. Never force push.' }
Write-Host 'GitHub main is up to date: https://github.com/shipshipliucixin1/innovation-dance'
