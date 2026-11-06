param([int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Dashboard environment missing. Run dashboard/setup.ps1 first.'
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'
$env:TEMP = Join-Path $PSScriptRoot '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
Push-Location $PSScriptRoot
try {
    Write-Host "Open http://localhost:$Port in your browser. Press Ctrl+C here to stop."
    & $pythonPath -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.port $Port --server.address 127.0.0.1 --server.headless true
    $dashboardExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $dashboardExit
