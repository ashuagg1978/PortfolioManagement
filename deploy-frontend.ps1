# Builds the React frontend against the EC2 backend and packs the contents of dist/ into frontend.zip.
#   .\deploy-frontend.ps1
#   .\deploy-frontend.ps1 -ApiBase http://other-host:8000 -Output C:\temp\site.zip
param(
    [string]$ApiBase = "http://54.252.208.209:8000",
    [string]$Output = (Join-Path $PSScriptRoot "frontend.zip")
)

$ErrorActionPreference = "Stop"

# 1. Build with the backend URL baked in (a static host has no /api proxy)
Push-Location (Join-Path $PSScriptRoot "frontend")
try {
    $env:VITE_API_BASE = $ApiBase
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
    Remove-Item Env:VITE_API_BASE -ErrorAction SilentlyContinue
    Pop-Location
}

# 2. Zip the contents of dist/ (index.html and assets/ at the zip root, not the dist folder itself)
$dist = Join-Path $PSScriptRoot "frontend\dist"
$py = @"
import os, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, src).replace(os.sep, "/"))
"@
$pyFile = Join-Path $env:TEMP "make_frontend_zip.py"
Set-Content -Path $pyFile -Value $py -Encoding ascii
python -I $pyFile $dist $Output
if ($LASTEXITCODE -ne 0) { throw "Zip creation failed" }

Write-Host "`nCreated $Output ($([math]::Round((Get-Item $Output).Length / 1MB, 1)) MB)"
