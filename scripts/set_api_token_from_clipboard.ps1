$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
  throw ".env file not found: $EnvPath"
}

$ClipboardValue = Get-Clipboard -Raw
if ([string]::IsNullOrWhiteSpace($ClipboardValue)) {
  throw "Clipboard is empty. Click 'Copy token to clipboard' in the ERPNext API Keys dialog first."
}

$Token = $ClipboardValue.Trim()
$Token = $Token -replace "`r", "" -replace "`n", ""

if ($Token.StartsWith("token ", [System.StringComparison]::OrdinalIgnoreCase)) {
  $Token = $Token.Substring(6).Trim()
}

if ($Token -match "^[^,]+,[^,]+$") {
  $Token = $Token -replace ",", ":"
}

if ($Token -notmatch "^[^:]+:[^:]+$") {
  throw "Clipboard must contain ERPNext token in API_KEY:API_SECRET or API_KEY,API_SECRET format. Click 'Copy token to clipboard' in ERPNext first."
}

$Parts = $Token.Split(":", 2)
$ApiKey = $Parts[0].Trim()
$ApiSecret = $Parts[1].Trim()

function Set-EnvValue {
  param(
    [string] $Content,
    [string] $Name,
    [string] $Value
  )

  $EscapedName = [regex]::Escape($Name)
  if ($Content -match "(?m)^$EscapedName=") {
    return ($Content -replace "(?m)^$EscapedName=.*$", "$Name=$Value")
  }

  return ($Content.TrimEnd() + "`n$Name=$Value`n")
}

$Content = Get-Content -Raw -LiteralPath $EnvPath
$Content = Set-EnvValue -Content $Content -Name "ERPNEXT_API_KEY" -Value $ApiKey
$Content = Set-EnvValue -Content $Content -Name "ERPNEXT_API_SECRET" -Value $ApiSecret
Set-Content -LiteralPath $EnvPath -Value $Content -Encoding utf8

Write-Host "ERPNext API token stored in .env. Values hidden."
