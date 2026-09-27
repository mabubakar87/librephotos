# Choose the GPU backend only when a capable NVIDIA card is present.
# 8 GB and compute capability 7.0 are enough for Moondream, Mistral Q5,
# SigLIP, CLIP, and buffalo_sc. Otherwise the CPU image is left in place.
$ErrorActionPreference = "Stop"
$override = Join-Path $PSScriptRoot "docker-compose.override.yml"
$tag = "latest"
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^tag=(.+)$') { $tag = $Matches[1].Trim() }
    }
}

$capable = $false
$reason = "nvidia-smi is not available"
try {
    $lines = & nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader,nounits
    foreach ($line in @($lines)) {
        $parts = $line.Split(",") | ForEach-Object { $_.Trim() }
        if ($parts.Count -lt 3) { continue }
        $name = $parts[0]
        $memoryMb = [double]$parts[1]
        $computeCap = [double]$parts[2]
        if ($memoryMb -ge 8192 -and $computeCap -ge 7.0) {
            $capable = $true
            $reason = "$name ${memoryMb} MiB, compute $computeCap"
            break
        }
        $reason = "$name has ${memoryMb} MiB and compute $computeCap, below 8192 MiB or compute 7.0"
    }
} catch {
    $reason = "nvidia-smi failed: $($_.Exception.Message)"
}

if ($capable) {
    $block = @"
    image: reallibrephotos/librephotos-gpu:${tag}
    gpus: all
"@
    Write-Host "GPU selected: $reason"
} else {
    $block = "    # CPU image: $reason"
    Write-Host "CPU selected: $reason"
}

$text = [System.IO.File]::ReadAllText($override)
$pattern = "(?s)(    # device-selection:start\r?\n).*?(    # device-selection:end)"
$replacement = "`${1}$block`n`${2}"
$updated = [regex]::Replace($text, $pattern, $replacement)
if ($updated -eq $text) {
    throw "device-selection markers were not found in docker-compose.override.yml"
}
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($override, ($updated -replace "`r`n", "`n" -replace "`r", "`n"), $utf8)
