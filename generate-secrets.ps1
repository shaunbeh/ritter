<#
.SYNOPSIS
    Generates a local modules/.env (gitignored) with fresh, unique secrets for this stack.

.DESCRIPTION
    modules/.env.example only holds placeholder values - nobody should share or commit real
    secrets there. Run this script once per environment to produce modules/.env with your own
    random JWT keys / SQL Server sa password / MinIO credentials, based on the .env.example
    template. Non-secret settings (SMTP, domains, etc.) are copied through unchanged - edit
    modules/.env afterwards to fill those in for your environment.

.EXAMPLE
    ./generate-secrets.ps1
#>
param(
    [string]$EnvExamplePath = (Join-Path $PSScriptRoot '.env.example'),
    [string]$EnvOutputPath = (Join-Path $PSScriptRoot '.env')
)

function New-Base64Secret {
    param([int]$Bytes = 32)
    $buffer = [byte[]]::new($Bytes)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer)
}

function New-StrongPassword {
    param([int]$Length = 24)
    $upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    $lower = 'abcdefghijkmnopqrstuvwxyz'
    $digits = '23456789'
    $symbols = '@-_.~'
    $all = $upper + $lower + $digits + $symbols

    $required = @(
        $upper[(Get-Random -Maximum $upper.Length)]
        $lower[(Get-Random -Maximum $lower.Length)]
        $digits[(Get-Random -Maximum $digits.Length)]
        $symbols[(Get-Random -Maximum $symbols.Length)]
    )
    $rest = [byte[]]::new($Length)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($rest)
    $randomChars = $rest | ForEach-Object { $all[$_ % $all.Length] }

    # required chars first guarantee SQL Server's password-complexity policy is met
    return -join ($required + $randomChars)
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
    'MSSQL_SA_PASSWORD'                       = New-StrongPassword
    'MINIO_ROOT_USER'                         = 'riteradmin'
    'MINIO_ROOT_PASSWORD'                     = New-StrongPassword
    'Host__Security__Jwt__SecretKey'          = New-Base64Secret
    'Host__Security__Jwt__EncryptionKey'      = New-Base64Secret
    'Host__Security__Jwt__RefreshTokenSecret' = New-Base64Secret
}

$content = Get-Content -LiteralPath $EnvExamplePath -Raw
foreach ($key in $secrets.Keys) {
    $pattern = "(?m)^$([regex]::Escape($key))=.*$"
    $evaluator = [System.Text.RegularExpressions.MatchEvaluator] { param($m) "$key=$($secrets[$key])" }
    $content = [System.Text.RegularExpressions.Regex]::Replace($content, $pattern, $evaluator)
}

Set-Content -LiteralPath $EnvOutputPath -Value $content -NoNewline
Write-Host "Wrote $EnvOutputPath with freshly generated secrets." -ForegroundColor Green
Write-Host "Review the remaining placeholder values (SMTP, domains, etc.) before running docker compose." -ForegroundColor Yellow
