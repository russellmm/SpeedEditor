$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv-win\Scripts\python.exe')) {
    throw 'Run .\setup.ps1 first.'
}
& .\.venv-win\Scripts\python.exe -m speededitor @args
exit $LASTEXITCODE
