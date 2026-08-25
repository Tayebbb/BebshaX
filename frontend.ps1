Push-Location "$PSScriptRoot/apps/frontend"
try {
    npm run dev
} finally {
    Pop-Location
}
