$ErrorActionPreference = "Stop"

$excludeFilePatterns = @(
    "ipssi-*.json",
    ".env",
    ".env.*"
)

$excludePathRegexes = @(
    "(^|/)\.venv/",
    "(^|/)venv/",
    "(^|/)__pycache__/",
    "(^|/)site-packages/",
    "(^|/)\.git/"
)

$regexes = @(
    "sk-[A-Za-z0-9]{20,}",
    "-----BEGIN PRIVATE KEY-----",
    "OPENAI_API_KEY\s*=\s*['""][^'""]+['""]"
)

$findings = @()
$files = Get-ChildItem -Recurse -File

foreach ($file in $files) {
    if ((Resolve-Path $file.FullName).Path -eq (Resolve-Path $PSCommandPath).Path) {
        continue
    }

    $relative = Resolve-Path -Relative $file.FullName
    $normalized = $relative.ToLower().Replace("\", "/")
    if ($normalized.StartsWith("./")) {
        $normalized = $normalized.Substring(2)
    }

    $skip = $false

    foreach ($pattern in $excludeFilePatterns) {
        if ($file.Name -like $pattern) {
            $skip = $true
            break
        }
    }

    if (-not $skip) {
        foreach ($pathRegex in $excludePathRegexes) {
            if ($normalized -match $pathRegex) {
                $skip = $true
                break
            }
        }
    }

    if ($skip) {
        continue
    }

    foreach ($regex in $regexes) {
        $matches = Select-String -Path $file.FullName -Pattern $regex -AllMatches
        if ($matches) {
            foreach ($m in $matches) {
                $findings += [PSCustomObject]@{
                    File = $relative
                    Line = $m.LineNumber
                    Pattern = $regex
                }
            }
        }
    }
}

if ($findings.Count -gt 0) {
    Write-Host "Secrets potentiels detectes:" -ForegroundColor Red
    $findings | Format-Table -AutoSize
    exit 1
}

Write-Host "OK: aucun secret detecte dans les fichiers suivis par le scan." -ForegroundColor Green
