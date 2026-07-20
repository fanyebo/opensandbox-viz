$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$appendPath = "D:\projects\opensandbox-viz\github-hosts.txt"
$resultPath = "D:\projects\opensandbox-viz\hosts-result.txt"

try {
    $current = Get-Content $hostsPath -Raw
    $append = Get-Content $appendPath -Raw

    # Check if already present
    if ($current -match "GitHub Hosts") {
        # Replace existing GitHub section
        $current = $current -replace "(?s)# ===== GitHub Hosts.*# ===== GitHub Hosts End =====\r?\n?", ""
    }

    # Ensure trailing newline
    if (-not $current.EndsWith("`r`n")) {
        $current = $current.TrimEnd() + "`r`n`r`n"
    }

    $newContent = $current + $append
    Set-Content -Path $hostsPath -Value $newContent -Encoding ASCII -NoNewline
    # Flush DNS
    ipconfig /flushdns | Out-Null
    "OK: hosts updated and DNS flushed" | Out-File $resultPath
} catch {
    "ERROR: $_" | Out-File $resultPath
}
