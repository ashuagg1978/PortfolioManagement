# Deploys the backend to the EC2 instance: zip -> scp -> unpack, install deps, migrate, restart service.
#   .\deploy.ps1              redeploy code (keeps the server's existing portfolio.db)
#   .\deploy.ps1 -WithDb      also upload your local portfolio.db (overwrites the server's)
param(
    [string]$HostName = "54.252.208.209",
    [string]$User = "ubuntu",
    [string]$Key = (Join-Path $PSScriptRoot "key-backend-key.pem"),
    [switch]$WithDb
)

$ErrorActionPreference = "Stop"
$target = "$User@$HostName"
$sshOpts = @("-i", $Key, "-o", "StrictHostKeyChecking=accept-new")
$tmp = Join-Path $env:TEMP "portfolio-deploy"
New-Item -ItemType Directory -Force $tmp | Out-Null

# 1. Build the zip with forward-slash entry names (Compress-Archive in PS 5.1 writes backslashes)
$zip = Join-Path $tmp "backend.zip"
$dbFlag = if ($WithDb) { "1" } else { "0" }
$py = @"
import os, sys, zipfile
src, out, with_db = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
skip_dirs = {"__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "tests"}
skip_files = {"portfolio.db-wal", "portfolio.db-shm"}
if not with_db:
    skip_files.add("portfolio.db")
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f in skip_files or f.endswith(".pyc"):
                continue
            p = os.path.join(root, f)
            z.write(p, "backend/" + os.path.relpath(p, src).replace(os.sep, "/"))
"@
$pyFile = Join-Path $tmp "make_zip.py"
Set-Content -Path $pyFile -Value $py -Encoding ascii
python -I $pyFile (Join-Path $PSScriptRoot "backend") $zip $dbFlag
if ($LASTEXITCODE -ne 0) { throw "Zip creation failed" }
Write-Host "Created $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"

# 2. Remote setup script (LF line endings, written without BOM)
$remote = @'
set -euo pipefail
cd ~
command -v unzip >/dev/null && dpkg -s python3-venv >/dev/null 2>&1 || {
    sudo apt-get update -y && sudo apt-get install -y unzip python3-venv
}
unzip -o backend.zip
cd backend
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m alembic upgrade head

if [ ! -f /etc/systemd/system/portfolio.service ]; then
    sudo tee /etc/systemd/system/portfolio.service >/dev/null <<UNIT
[Unit]
Description=Portfolio Management API
After=network.target

[Service]
User=$USER
WorkingDirectory=$HOME/backend
ExecStart=$HOME/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
    sudo systemctl daemon-reload
    sudo systemctl enable portfolio
fi
sudo systemctl restart portfolio
sleep 2
systemctl is-active portfolio
curl -s localhost:8000/docs -o /dev/null -w "docs endpoint: HTTP %{http_code}\n"
'@
$remoteFile = Join-Path $tmp "remote_setup.sh"
[System.IO.File]::WriteAllText($remoteFile, ($remote -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))

# 3. Upload and run
scp @sshOpts $zip $remoteFile "${target}:~/"
if ($LASTEXITCODE -ne 0) { throw "scp failed" }
ssh @sshOpts $target "bash ~/remote_setup.sh"
if ($LASTEXITCODE -ne 0) { throw "Remote setup failed" }

Write-Host "`nDone. API: http://${HostName}:8000/docs (port 8000 must be open in the EC2 security group)"
