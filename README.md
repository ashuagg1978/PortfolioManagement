# Mutual Funds Portfolio Manager

A web app that replaces `MFs Portfolio Dashboard.xlsx`: tracks mutual fund investments across
multiple accounts, computes accurate profitability (including XIRR), handles redemptions with
FIFO capital-gains accounting, tracks SIPs, and syncs NAVs on demand from the official AMFI feed.

React + TypeScript frontend, FastAPI + SQLAlchemy backend, a single local SQLite file for storage.
No database server, no Docker, no cloud account needed to run it - see [Local-first, deploy later](#local-first-deploy-later)
for what changes if this ever needs to move to GCP.

For full schema and API detail, see **[DATABASE.md](DATABASE.md)** and **[API.md](API.md)**.

## What it does

- **Multiple accounts** - tracks holdings separately per brokerage/RTA relationship (e.g. "ICICI
  Direct - Ashu", "Zerodha - Hars"), all rolled up into one dashboard.
- **On-demand NAV sync** - a "Sync NAV" button pulls the full AMFI `NAVAll.txt` feed
  (~14,000 schemes) and updates every scheme's latest NAV. No cron job, no background scheduler.
- **Scheme identification by AMFI Scheme Code** - the only reliable key, because AMFI scheme names
  are not unique (the same fund appears under several codes for Direct/Regular x Growth/IDCW
  variants) and Plan/Option fields are blank on much of the feed. A **Scheme Map** lets you attach
  your own display name and reconcile the raw names your broker statements use.
- **Purchases and redemptions, with commission derived, not entered.** Every transaction is
  entered the same way - quantity, NAV, and the final amount that moved at your bank - and
  commission (stamp duty, STT, exit load, GST, whatever your broker charged) is derived from those
  three numbers. The formula flips by direction: on a purchase you pay charges *on top of* what
  reaches the fund; on a redemption, charges come *out of* the proceeds. See
  [DATABASE.md](DATABASE.md#commission) for the exact arithmetic.
- **FIFO capital gains.** Redemptions consume the oldest purchased lots first (as Indian mutual
  fund tax law requires), giving a correct realized gain and an automatic STCG/LTCG split.
- **Soft delete.** Deleting a transaction flags it rather than removing it, so it drops out of
  every calculation immediately but stays in the database for audit.
- **SIP tracking that never guesses a NAV.** A SIP mandate (amount, frequency, start date, optional
  end date) is just a schedule. Nothing is written to the ledger automatically - the **Entries
  Due** page lists every occurrence whose date has arrived and asks you for the real NAV and units
  from your statement (the AMFI feed only ever has *today's* NAV, so a past SIP date has no NAV to
  guess from). Confirm turns it into a transaction; Skip marks a bounced/missed mandate without
  inventing a fake one.
- **Statement import.** Upload the legacy workbook (or, later, any broker statement in the same
  shape) through a three-step wizard: parse and stage → resolve any unmapped scheme names or
  accounts → commit. Duplicate rows are detected and skipped automatically.
- **Dashboard KPIs and a sortable per-scheme table**: Net Invested, Current Value, Net Gain/Loss,
  Total Return %, Active Schemes, portfolio XIRR, total commission paid, and an 11-column,
  click-to-sort breakdown per scheme (units, avg cost NAV, latest NAV, gain/loss, % gain, status,
  scheme-level XIRR).

## Project layout

```
backend/                FastAPI app - main.py is the entry point (`uvicorn main:app`)
  models/               SQLAlchemy ORM models (11 tables)
  services/              business logic - see DATABASE.md and API.md for what lives where
  api/routes/            HTTP routes, thin wrappers over services/
  schemas/               Pydantic request/response models
  db/                     engine, session, the Money/Nav/Units decimal column types
  core/config.py          Settings (env-var driven, every value has a default)
  data/nse_holidays.json  seeded NSE trading-holiday calendar
  alembic/                schema migrations
  scripts/seed.py         seeds the single user, 5 accounts, holiday calendar
  scripts/                run with `python -m scripts.<name>`
  tests/                  pytest - unit tests for every pure service, integration tests over HTTP
frontend/                 React 18 + TypeScript + Vite
  src/
    routes/                one file per page (Dashboard, Transactions, Sips, SipEntriesDue, Import)
    components/            shared UI (HoldingsTable, CommissionField, SchemeSearchInput, ...)
    lib/api.ts              typed fetch wrapper - the only place that knows the HTTP shape
    types/api.ts            TypeScript types mirroring backend/schemas/*.py
MFs Portfolio Dashboard.xlsx   the workbook this app replaces - also the reference dataset used
                                to validate the numbers (see the reconciliation note below)
```

## Running it locally

Requires Python 3.14+ and Node 20+ (tested on Python 3.14.0, Node 24.13.1).

### Backend

```bash
cd backend
python -m venv ../.venv        # if you don't already have one
../.venv/Scripts/activate      # Windows; use ../.venv/bin/activate on macOS/Linux
pip install -r requirements.txt

alembic upgrade head           # creates portfolio.db and applies the schema
python -m scripts.seed         # seeds the user, 5 accounts, and the holiday calendar

uvicorn main:app --reload  # http://localhost:8000, docs at /docs
```

No `.env` file is required - every setting has a working default (see `.env.example`). The
database is a single file, `backend/portfolio.db`; back it up by copying that file (the app should
be stopped first, or use `sqlite3 portfolio.db ".backup backup.db"` for an online-safe copy).

### Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

The dev server proxies `/api/*` to `http://localhost:8000` (see `vite.config.ts`), so both servers
just need to be running - no CORS configuration needed in development.

### First run

1. Open `http://localhost:5173`.
2. Click **Sync NAV** on the dashboard to pull current prices for all ~14,000 AMFI schemes.
3. Either add transactions by hand under **Transactions**, or go to **Import** and upload
   `MFs Portfolio Dashboard.xlsx` to bring in the existing history.
4. Set up any recurring investments under **SIPs** - actual entries appear on **Entries Due** as
   their dates arrive.

## Testing

```bash
cd backend
pytest                          # unit tests (parsing, FIFO, XIRR, SIP scheduling, commission) +
                                 # integration tests over the real HTTP routes against a throwaway
                                 # SQLite file per test. One test does a live network NAV sync;
                                 # another imports the real workbook end-to-end if present.
```

```bash
cd frontend
npm run typecheck               # tsc -b --noEmit
npm run build                   # production build (also typechecks)
```

## Design notes worth knowing before changing code

- **Money is exact.** SQLite has no decimal type, so a plain `Numeric` column silently becomes
  float and drifts. Every money/NAV/units column instead uses a custom `DecimalText` type
  (`backend/db/types.py`) that stores `Decimal` as fixed-precision text and round-trips
  exactly. The trade-off: SQL `SUM()`/`ORDER BY` don't work on these columns - all aggregation
  happens in Python, in the service layer.
- **Nothing is auto-generated into the ledger.** Not SIP occurrences, not import rows before
  commit. A transaction exists only once a human has confirmed the real NAV and units for it.
- **Commission is always derived, never entered** - see [DATABASE.md](DATABASE.md#commission).
- **Realized gain, FIFO lots, and XIRR are all computed on read, never stored.** Editing or
  soft-deleting an old transaction is reflected immediately everywhere, with no stale cached
  figures to invalidate.
- Full rationale for every one of these choices - what changed, why, and what was already broken
  in the workbook - lives in [DATABASE.md](DATABASE.md) and [API.md](API.md).

## Reconciliation against the workbook

The workbook's own `MFwise` sheet was used as the source of truth to validate this app's numbers:
`backend/scripts/reconcile.py`-style checks were run manually (import the workbook through
`/api/imports`, compare Net Invested/Current Value/XIRR per scheme). Two genuine data issues
surfaced in the workbook itself during that process - not bugs in this app - and are worth fixing
at the source before they're relied on:
- One purchase row (Txn-Maniqm-Ashu) has NAV x units off from the recorded amount by about ₹36,
  beyond ordinary rounding noise.
- One purchase row (Txn-Maniqm-Hars, 2021) has no NAV recorded at all for a ₹500,000 transaction.
- One transaction (Txn-Zerodh-Hars) appears to be entered twice.

Everything else - 619 of 632 rows (98%) - imports and commits cleanly. The remaining unmapped rows
are schemes from AMCs that were acquired/merged (L&T → HSBC in 2022, Principal → Sundaram in 2021)
and need a human decision about which successor scheme to map them to.

## Local-first, deploy later

This app deliberately runs entirely on your machine today - no Docker, no Cloud SQL, no GCP
project. It's built 12-factor enough that moving it later is additive, not a rewrite:

- **Frontend**: `npm run build` → static files → Firebase Hosting or a GCS bucket behind Cloud CDN.
- **Backend**: containerize as-is → Cloud Run, reading `DATABASE_URL` from the environment
  (already how it works locally).
- **Database**: the one piece that doesn't lift-and-shift. Cloud Run's filesystem is ephemeral, so
  the SQLite file would be wiped on every container restart. When that day comes, either mount a
  Filestore/NFS volume and pin the service to a single instance, or point `DATABASE_URL` at a
  managed Postgres - the codebase keeps that cheap on purpose (generic SQLAlchemy types, the one
  SQLite-specific call isolated in `db/upsert.py`, Alembic already managing the schema, and
  aggregation done in Python rather than SQL).
