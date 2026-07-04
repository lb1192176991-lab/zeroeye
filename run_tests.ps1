# Run deterministic seed tests on Windows — Kickama bounty #2
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m unittest discover -s tests -p "test_*.py" -v
Write-Host "OK: deterministic seed tests passed"
