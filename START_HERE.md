# Start Here (Windows)

## One-time setup

Open a PowerShell terminal in the repository folder (`PortfolioManagement`). The project requires Python 3.14 or newer and Node.js 20 or newer. This machine currently has Python 3.11 available through the launcher, so install Python 3.14 first:

```powershell
py install 3.14
```

Then create the virtual environment and install backend dependencies:

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install frontend dependencies once:

```powershell
Set-Location frontend
npm.cmd install
Set-Location ..
```

`npm.cmd` works around this machine's PowerShell policy, which blocks the `npm.ps1` command.

## Start the app

Open **two** PowerShell terminals in VS Code, both starting in the repository folder.

In terminal 1, prepare the local database and start the API:

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m alembic upgrade head
& ..\.venv\Scripts\python.exe -m scripts.seed
& ..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

In terminal 2, start the web app:

```powershell
Set-Location frontend
npm.cmd run dev
```

Open **http://localhost:5173**. The API is at **http://localhost:8000**, with interactive docs at **http://localhost:8000/docs**. Keep both terminals running while using the app.

The SQLite database is stored at `backend/portfolio.db`. The seed command is safe to rerun; keep a backup of that database before making manual changes to it.
