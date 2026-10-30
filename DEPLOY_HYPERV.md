# Deploying Portfolio Management on a Hyper-V Windows Server 2025 VM

This guide records the working procedure for hosting the app on a Windows Server 2025 VM under Hyper-V and publishing it over HTTPS with a Cloudflare Tunnel. It also lists the problems hit along the way and their fixes.

## Architecture

```
Browser --HTTPS--> Cloudflare --tunnel--> cloudflared (VM) --> Caddy :80 --+--> /api/*, /health --> uvicorn 127.0.0.1:8000 (FastAPI + SQLite)
                                                                           +--> everything else --> C:\apps\portfolio\dist (React build)
```

| Component | Role | Windows service |
|---|---|---|
| uvicorn (FastAPI) | Backend API, bound to localhost only | `PortfolioApi` (NSSM) |
| Caddy | Serves the frontend build and proxies `/api` and `/health` | `Caddy` (NSSM) |
| cloudflared | Outbound tunnel to Cloudflare, provides the public HTTPS URL | `cloudflared` (NSSM) |

Folder layout on the VM:

```
C:\apps\portfolio\
  .venv\            Python virtual environment
  backend\          API code, portfolio.db, config.json, .env
  dist\             Built frontend (copied from frontend\dist)
  Caddyfile
```

## 1. Prepare the VM

- Create a Generation 2 VM with Windows Server 2025, at least 2 vCPU and 4 GB RAM.
- Virtual switch:
  - An **External** switch gives the VM a LAN IP, so other devices can reach `http://<vm-ip>/`.
  - The **Default Switch** (NAT) is enough if you only publish through the Cloudflare Tunnel, since the tunnel only makes outbound connections.
- Install Windows updates.

## 2. Install prerequisites

Run in an elevated PowerShell, then open a new window so PATH refreshes:

```powershell
winget install Python.Python.3.14
winget install OpenJS.NodeJS.LTS        # only needed to build on the VM
winget install Git.Git
winget install CaddyServer.Caddy
winget install NSSM.NSSM
winget install Cloudflare.cloudflared
```

## 3. Get the code onto the VM

Build the frontend on the dev machine and copy the results:

```powershell
cd frontend
npm.cmd run build
```

- Copy `backend\` (without `__pycache__`) to `C:\apps\portfolio\backend`.
- Copy `frontend\dist` to `C:\apps\portfolio\dist`.
- Copy the **working tree**, not just the last commit, if you have uncommitted changes. The login feature (`api/routes/auth.py`, the `user_auth` migration, and `PyJWT` in `requirements.txt`) must be present.

## 4. Backend setup

```powershell
cd C:\apps\portfolio
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd backend
copy config.example.json config.json      # set gemini_api_key
```

Create `backend\.env` **before** running migrations, so the bootstrap accounts get real credentials:

```
SEED_USER_PASSWORD=<strong password>
ADMIN_PASSWORD=<strong password>
AUTH_SECRET=<long random string>
DATABASE_URL=sqlite:///C:/apps/portfolio/backend/portfolio.db
```

Generate a secret with `python -c "import secrets;print(secrets.token_urlsafe(48))"`.

Then migrate and seed (or copy your existing `portfolio.db` while the app is stopped):

```powershell
..\.venv\Scripts\python -m alembic upgrade head
..\.venv\Scripts\python -m scripts.seed
```

Notes on `.env`:

- One `KEY=value` per line, no quotes around simple values, forward slashes in paths.
- List values take JSON, for example `CORS_ORIGINS=["http://192.168.1.50"]`.
- `CORS_ORIGINS` is not needed when everything is served through Caddy on one origin.
- Relative paths such as the default `sqlite:///./portfolio.db` and `.env` itself resolve against the process working directory. The absolute `DATABASE_URL` above avoids depending on it.

## 5. Run the backend as a service

```powershell
nssm install PortfolioApi C:\apps\portfolio\.venv\Scripts\python.exe
nssm set PortfolioApi AppParameters "-m uvicorn main:app --host 127.0.0.1 --port 8000"
nssm set PortfolioApi AppDirectory C:\apps\portfolio\backend
nssm set PortfolioApi Start SERVICE_AUTO_START
nssm start PortfolioApi
```

`AppDirectory` matters. A Windows service starts in `C:\Windows\System32`, so without it the app would create an empty `portfolio.db` there and ignore `backend\.env`.

Check it:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health      # status : ok
```

Every `/api` route requires a login token. Only `/health` and `/api/auth/login` are public, so `/api/dashboard` returns `{"detail":"Not authenticated"}` without one. That is expected and shows the backend and database are working.

## 6. Serve the frontend and proxy the API with Caddy

### 6.1 Pre-checks

```powershell
Test-Path C:\apps\portfolio\dist\index.html                                   # True
Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue # no output = port is free
caddy version
```

If port 80 is taken (often IIS, service `W3SVC`), stop and disable that service or use another port in the Caddyfile.

### 6.2 Create the Caddyfile

```powershell
@'
:80 {
    encode gzip

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle /health {
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        root * C:/apps/portfolio/dist
        try_files {path} /index.html
        file_server
    }
}
'@ | Set-Content -Path C:\apps\portfolio\Caddyfile -Encoding ascii
```

The closing `'@` must start at column 0. The `try_files` line returns `index.html` for client-side routes so a page refresh does not 404.

### 6.3 Validate, test, install the service

```powershell
cd C:\apps\portfolio
caddy validate --config Caddyfile           # Valid configuration
caddy run --config Caddyfile                # foreground test, Ctrl+C to stop

$caddy = (Get-Command caddy).Source
nssm install Caddy $caddy
nssm set Caddy AppParameters "run --config C:\apps\portfolio\Caddyfile"
nssm set Caddy AppDirectory C:\apps\portfolio
nssm set Caddy Start SERVICE_AUTO_START
nssm set Caddy AppStdout C:\apps\portfolio\caddy.log
nssm set Caddy AppStderr C:\apps\portfolio\caddy.log
nssm start Caddy
```

### 6.4 Test locally

```powershell
Invoke-WebRequest http://localhost/ -UseBasicParsing | Select-Object StatusCode    # 200
```

### 6.5 Optional: LAN access

Only if the VM is on an External switch and you want `http://<vm-ip>/` from other devices:

```powershell
New-NetFirewallRule -DisplayName "Portfolio HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
```

Do not open port 8000. Remove the rule if you only use the tunnel: `Remove-NetFirewallRule -DisplayName "Portfolio HTTP"`.

## 7. Publish with a Cloudflare Tunnel

Prerequisites: a free Cloudflare account and a domain whose nameservers point to Cloudflare (zone status **Active**).

### 7.1 Create the tunnel

```powershell
cloudflared tunnel login                    # browser opens, pick the domain
cloudflared tunnel create portfolio         # prints the tunnel ID and credentials JSON path
cloudflared tunnel route dns portfolio portfolio.<yourdomain>
```

This writes the credentials to `C:\Users\<you>\.cloudflared\<TUNNEL-ID>.json`.

### 7.2 Config for the service account

The Windows service runs as LocalSystem, so it reads its files from `C:\Windows\System32\config\systemprofile\.cloudflared\`, not your user profile. Copy the credentials there and create the config:

```powershell
$dst = "C:\Windows\System32\config\systemprofile\.cloudflared"
New-Item -ItemType Directory -Force $dst
Copy-Item C:\Users\<you>\.cloudflared\<TUNNEL-ID>.json $dst
```

`$dst\config.yml`:

```yaml
tunnel: <TUNNEL-ID>
credentials-file: C:\Windows\System32\config\systemprofile\.cloudflared\<TUNNEL-ID>.json

ingress:
  - hostname: portfolio.<yourdomain>
    service: http://localhost:80
  - service: http_status:404
```

### 7.3 Test in the foreground

```powershell
cloudflared tunnel run portfolio
```

You should see four `Registered tunnel connection` lines. Press Ctrl+C to stop.

### 7.4 Install as a service with NSSM

```powershell
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
nssm install cloudflared $cf
nssm set cloudflared AppParameters "--config C:\Windows\System32\config\systemprofile\.cloudflared\config.yml tunnel run portfolio"
nssm set cloudflared AppDirectory "C:\Program Files (x86)\cloudflared"
nssm set cloudflared Start SERVICE_AUTO_START
nssm set cloudflared AppStdout C:\apps\portfolio\cloudflared.log
nssm set cloudflared AppStderr C:\apps\portfolio\cloudflared.log
nssm start cloudflared
```

Verify:

```powershell
cloudflared tunnel info portfolio           # lists active connections
```

In the Cloudflare dashboard (Zero Trust, Networks, Tunnels) the tunnel should show **Healthy**.

### 7.5 Verify the public site

Open `https://portfolio.<yourdomain>` on a device that is not the VM, for example a phone on mobile data. The login page should load.

## 8. Security checklist

- Change the default admin and seed passwords. The code defaults are `password@123`. If the accounts already exist, `.env` changes will not alter them, so use the change-password feature (`POST /api/auth/change-password`).
- Set `AUTH_SECRET`. If unset, `backend\.auth_secret` is generated automatically. Include that file in backups.
- Consider **Cloudflare Access** (Zero Trust, Access, Applications) to put a one-time-PIN login in front of the app.
- Keep port 8000 closed and bound to `127.0.0.1`.
- Do not commit secrets or keys (`config.json`, `.env`, `.auth_secret`, `*.pem`). Rotate any that were committed, including database passwords in docs.

## 9. Backups

The data lives in `backend\portfolio.db` (plus `.auth_secret`). Stop `PortfolioApi`, copy the files, and start it again. Hyper-V checkpoints also work. Do not copy the `-wal` and `-shm` files unless the app was shut down cleanly.

## 10. Operations

| Task | Command |
|---|---|
| Check all services | `Get-Service PortfolioApi, Caddy, cloudflared` |
| Restart after `.env` or code change | `nssm restart PortfolioApi` |
| Restart after Caddyfile change | `nssm restart Caddy` |
| Restart after tunnel config change | `nssm restart cloudflared` |
| Deploy a new frontend | Replace the contents of `C:\apps\portfolio\dist` (no restart needed) |
| Deploy new backend code | Copy files, run `alembic upgrade head` if there are migrations, then restart `PortfolioApi` |
| Logs | `Get-Content C:\apps\portfolio\caddy.log -Tail 50`, same for `cloudflared.log` |

## Troubleshooting

### `{"detail":"Not authenticated"}` from `/api/dashboard`

Expected without a login. Get a token first:

```powershell
$r = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/auth/login -ContentType 'application/json' -Body '{"username":"admin","password":"<your password>"}'
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard -Headers @{Authorization="Bearer $($r.access_token)"}
```

Check `api/routes/auth.py` or `/docs` for the exact field names if you get a 422.

### Backend shows empty data or "no such table"

The process probably started in the wrong folder and created a new `portfolio.db`. Confirm `nssm get PortfolioApi AppDirectory` is `C:\apps\portfolio\backend`, or set the absolute `DATABASE_URL` in `.env`.

### Browser cannot reach `http://<vm-ip>/` from another machine

Check that the VM uses an External switch, the firewall rule exists, and `Get-Service Caddy` is Running.

### `winget install` succeeded but `cloudflared` is not recognised

The current window has a stale PATH. Refresh it or open a new window:

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

The MSI installs to `C:\Program Files (x86)\cloudflared\`.

### Tunnel works in the foreground but the dashboard says Down

Symptoms: `cloudflared tunnel info` reports no active connection, the Windows service shows Running (or hangs on stop), and `tunnel run` in a terminal works.

Cause: the service created by the MSI had no arguments (`sc.exe qc cloudflared` shows only the exe path), and as LocalSystem it could not see the config in your user profile.

Fix: copy the config and credentials to the `systemprofile\.cloudflared` folder (section 7.2), remove the old service, and recreate it with NSSM (section 7.4):

```powershell
Stop-Process -Name cloudflared -Force -ErrorAction SilentlyContinue
sc.exe delete cloudflared
```

### `sc.exe config ... binPath=` prints usage and changes nothing

Windows PowerShell 5.1 mangles the embedded quotes. Use NSSM instead, as in section 7.4.

### `Restart-Service cloudflared` loops on "Waiting for service to stop"

The service was hung because it had nothing to run. Kill it with `Stop-Process -Name cloudflared -Force` or `taskkill /F /IM cloudflared.exe`, then fix the service as above.

### Site does not load although the tunnel is Healthy

Check in this order:

1. **DNS record.** In the Cloudflare DNS page there must be a CNAME `portfolio` pointing to `<TUNNEL-ID>.cfargotunnel.com`, proxied. Create it with `cloudflared tunnel route dns portfolio portfolio.<yourdomain>`. This was missing in our case.
2. **Nameservers.** `nslookup -type=NS <yourdomain>` must list the two Cloudflare nameservers, and the zone must show Active.
3. **Hostname match.** The `hostname:` in `config.yml` and the tunnel route must equal the public hostname exactly.
4. **Origin reachable.** `Invoke-WebRequest http://localhost/ -UseBasicParsing` must return 200.

Browser error to cause:

| Error | Meaning |
|---|---|
| 1033 or 530 | Tunnel not connected |
| 502 | Tunnel is up but Caddy or `localhost:80` is not answering |
| 404 from Cloudflare | Hostname does not match an ingress rule |
| Cannot resolve / NXDOMAIN | DNS record missing or nameservers not switched |

### `curl` on the VM says "Could not resolve host" but the site works elsewhere

The VM's resolver (the Hyper-V Default Switch NAT forwarder) holds a stale or failed answer. A test with a forced IP proves the site itself is fine:

```powershell
nslookup portfolio.<yourdomain> 1.1.1.1
curl.exe -I --resolve portfolio.<yourdomain>:443:<ipv4-from-nslookup> https://portfolio.<yourdomain>    # HTTP 200
```

Verify from a phone on mobile data. To fix the VM's own DNS:

```powershell
Get-NetAdapter | Where-Object Status -eq Up | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses 1.1.1.1,8.8.8.8 }
ipconfig /flushdns
```

### Caddy will not start on port 80

Another process owns the port, usually IIS. Find it with `Get-NetTCPConnection -LocalPort 80 -State Listen`, stop it, or change the Caddyfile to another port.

### Caddyfile is rejected

Check that it is saved as plain ASCII or UTF-8 without BOM and is named `Caddyfile` with no `.txt`. Run `caddy fmt --overwrite Caddyfile`, then `caddy validate --config Caddyfile`.
