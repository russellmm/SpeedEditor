param([string]$PythonVersion = '3.13')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv-win\Scripts\python.exe')) {
    py "-$PythonVersion" -m venv .venv-win
    if ($LASTEXITCODE -ne 0) { throw "Install Python $PythonVersion with tkinter and the Python launcher, then retry." }
}
& .\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Write-Host 'Ready. Launch with .\run.ps1, or inspect with .\run.ps1 doctor'
