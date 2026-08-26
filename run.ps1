param (
    [string]$Target = "dev"
)

if ($Target -eq "backend") {
    node "$PSScriptRoot/scripts/run_backend.js"
} elseif ($Target -eq "frontend") {
    node "$PSScriptRoot/scripts/dev.js"
} else {
    node "$PSScriptRoot/scripts/dev.js"
}
