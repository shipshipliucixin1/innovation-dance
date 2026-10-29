$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectEnv = Join-Path $projectRoot '.conda-env'
$projectPython = Join-Path $projectEnv 'python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    if (Test-Path -LiteralPath $projectEnv) {
        throw 'Existing .conda-env is incomplete. It was not deleted or rebuilt. Inspect it manually before retrying.'
    }
    # Some Windows conda.exe launchers fail with DLL relocation errors. The same
    # Conda installation can run as python -m conda without changing that install.
    $condaPython = $null
    $candidates = @()
    if ($env:CONDA_PYTHON_EXE) { $candidates += $env:CONDA_PYTHON_EXE }
    $commands = @(Get-Command conda -All -ErrorAction SilentlyContinue)
    foreach ($command in $commands) {
        if ($command.Source) {
            $folder = Split-Path -Parent $command.Source
            for ($level=0; $level -lt 3; $level++) {
                $candidates += (Join-Path $folder 'python.exe')
                $folder = Split-Path -Parent $folder
                if (-not $folder) { break }
            }
        }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate) {
            & $candidate -m conda --version 2>$null
            if ($LASTEXITCODE -eq 0) { $condaPython = $candidate; break }
        }
    }
    if (-not $condaPython) {
        throw 'Conda could not be located. Install Miniconda, then run setup.bat from a Miniconda Prompt. No fallback installation was attempted.'
    }
    & $condaPython -m conda create --prefix $projectEnv python=3.11 pip -y
    if ($LASTEXITCODE -ne 0) { throw 'Project environment creation failed. No other environment will be used.' }
}
& $projectPython (Join-Path $PSScriptRoot 'verify_env.py')
if ($LASTEXITCODE -ne 0) { throw 'Interpreter verification failed. Installation stopped.' }
$requirements = @(Get-Content -LiteralPath (Join-Path $projectRoot 'requirements.txt') | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') })
if ($requirements.Count -gt 0) {
    & $projectPython -m pip install --disable-pip-version-check --no-cache-dir -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Project-only dependency installation failed.' }
} else {
    Write-Host 'Standard library only; no dependency installation required.'
}
Write-Host 'ProjectFlow setup complete. No base or unrelated environment was modified.'
