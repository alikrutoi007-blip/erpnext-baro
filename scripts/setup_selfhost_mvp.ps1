param(
  [switch] $UseClipboardToken
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Invoke-PythonStep {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Message,

    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [string[]] $Arguments = @()
  )

  Write-Host $Message
  & python $ScriptPath @Arguments

  if ($LASTEXITCODE -ne 0) {
    throw "Step failed with exit code ${LASTEXITCODE}: $ScriptPath $($Arguments -join ' ')"
  }
}

if ($UseClipboardToken) {
  powershell -ExecutionPolicy Bypass -File ".\scripts\set_api_token_from_clipboard.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Could not store ERPNext API token from clipboard."
  }
}

Invoke-PythonStep "Checking ERPNext API connection..." ".\scripts\check_connection.py"
Invoke-PythonStep "Creating Baro role profiles..." ".\scripts\create_role_profiles.py" @("--execute")
Invoke-PythonStep "Creating Repair Job DocType..." ".\scripts\create_repair_job_doctype.py" @("--execute")
Invoke-PythonStep "Creating Repair Job workflow..." ".\scripts\create_repair_job_workflow.py" @("--execute")
Invoke-PythonStep "Creating MVP project/backlog tasks..." ".\scripts\create_mvp_backlog_tasks.py" @("--execute")
Invoke-PythonStep "Verifying MVP setup..." ".\scripts\verify_mvp_setup.py"

Write-Host "Self-host ERPNext MVP setup finished. Check output above for any warnings."
