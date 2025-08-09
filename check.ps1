Clear-Host

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  CHECK EXECUTABLES IN PATH" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$executables = "flac", "rsgain"

$foundCount = 0
$notFoundCount = 0
$results = @{}

foreach ($executable in $executables) {
    Write-Host "   Checking: $executable..."

    if (Get-Command $executable -ErrorAction SilentlyContinue) {
        Write-Host "   Found: '$executable' is in the PATH." -ForegroundColor Green
        $foundCount++
        $results[$executable] = $true
    } else {
        Write-Host "   Not found: '$executable' is NOT in the PATH." -ForegroundColor Red
        $notFoundCount++
        $results[$executable] = $false
    }
    Write-Host ""
}
