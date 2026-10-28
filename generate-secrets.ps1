<#
.SYNOPSIS
    Writes a local .env (gitignored) with fresh secrets for the transcription stack.

.EXAMPLE
    ./generate-secrets.ps1
#>
param(
    [string]$EnvExamplePath = (Join-Path $PSScriptRoot '.env.example'),
    [string]$EnvOutputPath = (Join-Path $PSScriptRoot '.env')
)

function New-UrlSafeSecret {
    param([int]$Bytes = 32)
    $buffer = [byte[]]::new($Bytes)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

if (-not (Test-Path -LiteralPath $EnvExamplePath)) {
    throw "Template not found: $EnvExamplePath"
}
if (Test-Path -LiteralPath $EnvOutputPath) {
    $answer = Read-Host "$EnvOutputPath already exists. Overwrite? (y/N)"
    if ($answer -notin @('y', 'Y')) {
        Write-Host 'Aborted, existing .env left untouched.'
        return
    }
}

$secrets = [ordered]@{
    'POSTGRES_PASSWORD'    = New-UrlSafeSecret
    'MINIO_ROOT_PASSWORD'  = New-UrlSafeSecret
    'API_KEY'              = New-UrlSafeSecret
}

$content = Get-Content -LiteralPath $EnvExamplePath -Raw
foreach ($key in $secrets.Keys) {
    $pattern = "(?m)^$([regex]::Escape($key))=.*$"
    $evaluator = [System.Text.RegularExpressions.MatchEvaluator] { param($m) "$key=$($secrets[$key])" }
    $content = [System.Text.RegularExpressions.Regex]::Replace($content, $pattern, $evaluator)
}

Set-Content -LiteralPath $EnvOutputPath -Value $content -NoNewline
Write-Host "Wrote $EnvOutputPath with freshly generated secrets." -ForegroundColor Green
Write-Host "Set HF_TOKEN, and LLM_BASE_URL / LLM_MODEL if you want summaries, before starting the stack." -ForegroundColor Yellow
