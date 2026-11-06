$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = Join-Path $PSScriptRoot '.tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache/pip'
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:PIP_CACHE_DIR | Out-Null
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $existingPython = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $existingPython) {
        & $existingPython -m venv (Join-Path $PSScriptRoot '.venv')
    } else {
        py -3 -m venv (Join-Path $PSScriptRoot '.venv')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the dashboard Python environment.' }
}
& $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dashboard dependency installation failed.' }
Write-Host 'Ready. Run dashboard/run_dashboard.ps1 from the project root.'
