# Database

SQLite (`backend/portfolio.db`), managed by SQLAlchemy 2.0 + Alembic. 11 tables. See
[README.md](README.md#running-it-locally) for how to create/migrate it, and
[API.md](API.md) for how each table is exercised over HTTP.

## Money, NAV, and units are stored as text, not float

SQLite has no decimal storage class - SQLAlchemy's `Numeric` silently becomes `float` on this
dialect, and float drifts on ordinary arithmetic (`0.1 + 0.2 == 0.30000000000000004` in Python).
That's unacceptable for a financial ledger.

Every money/NAV/units column instead uses a custom `TypeDecorator`
(`backend/db/types.py`) that stores a `Decimal` as a fixed-precision **TEXT** string and
returns an exact `Decimal` on read:

| Type | Precision | Used for |
|---|---|---|
| `Money` | 2 decimal places | amounts, commission, gains |
| `Nav` | 4 decimal places | NAV (matches the AMFI feed's own precision) |
| `Units` | 6 decimal places | unit quantities |

**Trade-off, accepted deliberately:** `SUM()`, `AVG()`, and `ORDER BY` in raw SQL don't work
meaningfully on these columns - they're plain TEXT to the database engine. All aggregation
(FIFO lot walking, XIRR, dashboard totals) happens in Python, in the service layer. At this data
volume (low thousands of rows) that's microseconds of work, and the alternative - float drift in
a ledger - isn't a trade worth making.

At the API boundary, `backend/schemas/types.py` re-serializes these `Decimal` fields as plain
JSON numbers (Pydantic's default is a JSON *string*, which would break arithmetic in the browser).

## Two SQLite behaviors handled explicitly

- **Foreign keys are OFF by default.** `backend/db/session.py` issues `PRAGMA
  foreign_keys=ON` on every new connection - without it, every FK in this schema would be
  decorative.
- **`ALTER TABLE` can't drop or alter a column.** Alembic is configured with
  `render_as_batch=True` (`backend/alembic/env.py`), which rebuilds the table under the hood
  instead. Needed for any future migration beyond adding a column.

## Entity-relationship overview

```
users ──< accounts ──< transactions >── schemes ──< portfolio_schemes
  │                        │  ▲              │
  │                        │  └── sip_id      └──< scheme_aliases
  │                        │
  │                        └──< (soft-deleted, never hard-deleted)
  │
  ├──< sips ──< sip_skips
  │
  └──< import_batches ──< import_rows
```

`schemes` is the one global, non-user-scoped table - it's wholly owned by the AMFI feed and
overwritten on every NAV sync. Every other table is scoped to `user_id` (directly, or indirectly
through `account_id`/`sip_id`).

---

## Tables

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | string | |
| `email` | string, **unique** | |
| `password_hash` | string, nullable | scrypt hash (`core/security.py`). `email` is also the login username. |
| `is_admin` | bool | Can manage users. |
| `is_active` | bool | Disabled users cannot log in; their existing tokens stop working immediately. |

**CRUD:** create-only, via `scripts/seed.py` (idempotent - safe to re-run). No API routes; there's
exactly one user (`SEED_USER_EMAIL` in settings), resolved by `api/deps.py::get_current_user`.

---

### `accounts`

One brokerage/RTA relationship (e.g. "ICICI Direct - Ashu"). Everything else in the ledger hangs
off an account.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → `users.id` | |
| `account_name` | string | |
| `platform` | string | e.g. "ICICI Direct", "Zerodha" |

**Constraint:** unique (`user_id`, `account_name`).

**CRUD:** `GET /api/accounts`, `POST /api/accounts`, `PATCH /api/accounts/{id}` (rename or change
platform). No delete route - accounts are expected to be long-lived and few, and every transaction/
SIP/import batch references one by FK, so removing one isn't a simple soft-delete-and-move-on the
way a transaction is. `scripts/seed.py` creates the initial 5.

---

### `schemes`

The global, AMFI-feed-owned master list. Refreshed wholesale by every NAV sync
(`services/amfi.py::sync_navs`). **Not** where a user's own display name lives - see
`portfolio_schemes` below for why those are split.

| Column | Type | Notes |
|---|---|---|
| `scheme_code` | PK, string | AMFI's scheme code - the only reliable identifier (see below) |
| `scheme_name` | string, indexed | AMFI's own name - **not unique** |
| `isin_growth` | string, nullable | `-` in the feed becomes `NULL` |
| `isin_reinvestment` | string, nullable | |
| `plan` | string, nullable | "Direct Plan" / "Regular Plan" - **blank on ~44% of the feed** |
| `option` | string, nullable | "Growth" / "IDCW" / etc. - also frequently blank |
| `latest_nav` | `Nav`, nullable | |
| `nav_date` | date, nullable | Per-scheme, not global - dead schemes carry old dates |
| `updated_at` | datetime | Auto-updated on every sync |

**Why `scheme_code` is the only safe key:** the live AMFI feed was inspected directly while
building this - `Plan`/`Option` are empty on 6,301 of 14,288 rows (e.g. every "SBI FLEXICAP FUND"
row), so they can't disambiguate. `scheme_name` isn't unique either - "Nippon India ELSS Tax Saver
Fund" appears under 6 different codes (Direct/Regular × Growth/IDCW/Annual-IDCW). Every join in
this app goes through `scheme_code`.

**CRUD:** no direct create/update route - rows are upserted in bulk by `POST /api/nav/sync`
(`ON CONFLICT (scheme_code) DO UPDATE`, chunked at 1,000 rows/statement). The import pipeline also
inserts bare placeholder rows (name only, no NAV yet) for scheme codes it references before a sync
has reached them - see `services/imports.py::_ensure_scheme_placeholder`. Read via
`GET /api/schemes/search?q=`.

---

### `scheme_nav_history`

Daily NAV history, one row per scheme per day the NAV was synced - unlike `schemes.latest_nav`
above (current value only, overwritten on every sync), this is an append-only log feeding the
dashboard's value-over-time chart (`GET /api/dashboard/history`).

| Column | Type | Notes |
|---|---|---|
| `id` | PK, integer | Surrogate PK (not a composite key) so `insert_ignore`'s conflict target is a plain unique index, matching `transactions`' own style |
| `scheme_code` | FK → `schemes.scheme_code`, indexed | |
| `nav_date` | date | |
| `nav` | `Nav` | |

Unique index on `(scheme_code, nav_date)`. Rows are immutable once inserted - historical NAVs
don't get revised - so there's no `updated_at`.

**Why this table exists at all** (unlike everything else on this page, which is computed live -
see [Derived, never stored](#derived-never-stored) below): its source, the community
[mfapi.in](https://api.mfapi.in) API, has no server-side date filtering (verified live), so
fetching a scheme's history is always a full-history download. Doing that on every dashboard page
load would mean N slow third-party round-trips per visit; storing it once, refreshed only on
explicit "Sync NAV", is what keeps the dashboard fast.

**Scoped to held schemes only** - not the ~14,288-scheme AMFI universe `schemes` mirrors, just the
~15-30 schemes a real portfolio actually transacts (`services/portfolio_history.py::sync_nav_history`
finds these via `DISTINCT scheme_code` over the user's non-deleted transactions). This bounds the
table's size to `schemes_held × trading_days_since_first_txn` - tens of thousands of rows at most
for a portfolio several years old, a few MB on disk - trivial next to the 14,288-row AMFI feed this
app already fully upserts on every single current-NAV sync.

**CRUD:** no direct route - populated by `POST /api/nav/sync` via `insert_ignore` (`ON CONFLICT
(scheme_code, nav_date) DO NOTHING`), so re-syncing is a no-op for dates already stored. Read
indirectly through `GET /api/dashboard/history`, never returned raw.

---

### `portfolio_schemes`

A user's own display label for a scheme they hold, e.g. scheme_code `103196` →
*"Nippon India ELSS Tax Saver (Regular Growth)"* even though AMFI's own name is noisier.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → `users.id`, indexed | |
| `scheme_code` | FK → `schemes.scheme_code`, indexed | |
| `display_name` | string | |

**Constraint:** unique (`user_id`, `scheme_code`).

**Why this is a separate table from `schemes`:** the original design (one row per scheme, global
`display_name` column) breaks the moment two users hold the same fund under different labels, or a
NAV sync needs to overwrite a row the user has customized. Splitting the AMFI-owned master from
the user's label avoids both.

**CRUD:** written by the import pipeline when it seeds mappings from a workbook's "NAV Reference"
sheet. No dedicated route yet; used internally by `services/scheme_names.py::display_name_for`,
which every dashboard/SIP view calls to resolve a scheme's display name (falling back to the AMFI
name, then the bare code).

---

### `scheme_aliases`

Maps a raw name as it appears on a broker statement to a scheme code - built up whenever the
import wizard resolves an unmapped name.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → `users.id`, indexed | |
| `raw_name` | string | The exact text from the statement |
| `scheme_code` | FK → `schemes.scheme_code`, indexed | |

**Constraint:** unique (`user_id`, `raw_name`).

**CRUD:** created by `POST /api/imports/{batch_id}/mappings/scheme` (and seeded in bulk from a
workbook's own "Scheme Map" sheet on upload). Read by the import staging step to auto-resolve
future uploads without asking again.

---

### `transactions`

The ledger. Every confirmed purchase or redemption - manual, from a SIP confirmation, or from an
import - is one row here. **Nothing is ever written speculatively**: `nav` and `units` are
`NOT NULL`, meaning a row only exists once a human has supplied the real, confirmed values.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `account_id` | FK → `accounts.id`, indexed | |
| `scheme_code` | FK → `schemes.scheme_code`, indexed | |
| `transaction_date` | date, indexed | |
| `type` | string | `PURCHASE` \| `REDEMPTION` - *what* happened |
| `source` | string | `MANUAL` \| `SIP` \| `IMPORT` - *where it came from* |
| `sip_id` | FK → `sips.id`, nullable | Set only when `source = SIP` |
| `sip_scheduled_date` | date, nullable | The *raw*, unadjusted SIP occurrence date - see below |
| `amount` | `Money` | The actual money that moved at the bank |
| `nav` | `Nav` | **NOT NULL** |
| `units` | `Units` | **NOT NULL** |
| `commission` | `Money`, default 0 | Derived, not entered - see [Commission](#commission) |
| `signed_amount` | `Money` | `-amount` for PURCHASE, `+amount` for REDEMPTION |
| `folio_no` | string, nullable | |
| `status` | string, nullable | Free-text annotation (e.g. carried over from an import) |
| `source_hash` | string, indexed | Dedupe key - see below |
| `is_deleted` | boolean, default false | **Soft delete** - see below |
| `created_at` | datetime | |

**Constraints:**
- Unique (`account_id`, `source_hash`) - the general dedupe key. `source_hash` is
  `sha256(account_id, scheme_code, date, type, amount, units, folio_no)`
  (`services/transactions.py::compute_source_hash`).
- **Partial** unique index on (`sip_id`, `sip_scheduled_date`), `WHERE sip_id IS NOT NULL` - the
  SIP idempotency key. Confirming the same due entry twice is a no-op, not an error, because
  `sip_scheduled_date` is the *unadjusted* calendar date the SIP was scheduled for, independent of
  the trading-holiday calendar that produced the actual `transaction_date`. That separation means
  a later change to the holiday calendar can't silently create a duplicate for a date that was
  already confirmed under an older calendar.
- Index on (`account_id`, `scheme_code`, `transaction_date`) for the FIFO/dashboard queries.

**Type vs. source, and why they're separate fields:** a SIP credit *is* a purchase - collapsing
"what happened" and "where it came from" into one enum (as a naive `type ∈ {Purchase, Redemption,
SIP}` would) makes a SIP redemption inexpressible and loses the distinction between a manually
entered purchase and an imported one.

**Soft delete:** `DELETE /api/transactions/{id}` sets `is_deleted = true`; the row is never
removed. Every query that feeds a calculation (`services/portfolio.py`,
`services/fifo.py`, `services/transactions.py::_units_held`) filters `is_deleted = false`,
so a deleted transaction drops out of every dashboard figure immediately and reversibly
(`POST /api/transactions/{id}/restore`).

**Nothing derived here is stored beyond what was entered.** Realized gain, FIFO lot cost, and
XIRR are recomputed from this table on every read - see [Derived, never stored](#derived-never-stored).

**CRUD:** `GET/POST/PATCH/DELETE /api/transactions`, `POST /api/transactions/{id}/restore` - full
detail in [API.md](API.md#transactions).

---

### `sips`

A SIP mandate definition - amount, frequency, start/end date. **Not** a log of what was invested;
that's what `transactions` (with `source = SIP`) is for.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `account_id` | FK → `accounts.id`, indexed | |
| `scheme_code` | FK → `schemes.scheme_code`, indexed | |
| `amount` | `Money` | The fixed amount the mandate debits |
| `frequency` | string | `MONTHLY` \| `BIWEEKLY` |
| `start_date` | date | |
| `end_date` | date, nullable | `NULL` = perpetual |
| `folio_no` | string, nullable | |
| `is_active` | boolean, default true | |
| `parent_sip_id` | FK → `sips.id`, nullable, self-referential | See versioning below |
| `created_at` | datetime | |

**Editing an active SIP uses "close and clone", not an in-place update.**
`POST /api/sips/{id}/version` sets the *current* row's `end_date` to the day before the change and
`is_active = false`, then inserts a **new** row (new `start_date`, new `amount`/`frequency` as
requested, `parent_sip_id` pointing back to the old row). This preserves exact history of what was
scheduled at any point in the past - an in-place update would make it impossible to reconstruct
what a SIP's terms were on a given historical date.

**No occurrence is ever auto-generated from this table.** `services/sip_schedule.py` projects
occurrences on read; `services/sips.py::due_entries` diffs those against `transactions` and
`sip_skips` to find what's outstanding. See [SIP execution model](#sip-execution-model).

**CRUD:** `GET/POST /api/sips`, `POST /api/sips/{id}/version` - detail in
[API.md](API.md#sips).

---

### `sip_skips`

Records a scheduled SIP occurrence the user has confirmed **never executed** (bounced mandate,
insufficient funds) - the only way to make an occurrence stop appearing on the Entries Due page
without fabricating a transaction for it.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `sip_id` | FK → `sips.id`, indexed | |
| `scheduled_date` | date | The unadjusted occurrence date being skipped |
| `reason` | string, nullable | |
| `created_at` | datetime | |

**Constraint:** unique (`sip_id`, `scheduled_date`).

**CRUD:** `POST /api/sips/due/skip`. No update/delete route - skip a different date, or re-confirm
the SIP's terms via versioning, rather than editing history.

---

### `market_holidays`

The NSE trading-holiday calendar used to roll a SIP's scheduled date forward when it lands on a
weekend or holiday.

| Column | Type | Notes |
|---|---|---|
| `holiday_date` | PK, date | |
| `exchange` | string, default `NSE` | |
| `description` | string, nullable | |

**CRUD:** seeded from `backend/data/nse_holidays.json` by `scripts/seed.py` (idempotent). No
API route yet - edit the JSON file and re-run the seed script to add more years.

**Known limitation:** the seeded calendar covers 2024-2026. A SIP occurrence in an unseeded year
degrades to weekend-only adjustment; `services/sip_schedule.py` flags this per-occurrence via
`calendar_complete: false` rather than silently producing a possibly-wrong date - surfaced in the
UI as an "uncertain date" badge.

---

### `import_batches` / `import_rows`

The staging area for the two-phase import pipeline (upload → resolve → commit). Persisting parsed
rows here - rather than holding them in server memory - is what lets preview and commit be two
separate, stateless HTTP calls, and doubles as an audit trail.

**`import_batches`**

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → `users.id`, indexed | |
| `filename` | string | |
| `status` | string | `PENDING` \| `COMMITTED` |
| `created_at` | datetime | |
| `committed_at` | datetime, nullable | |

**`import_rows`**

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `batch_id` | FK → `import_batches.id`, indexed | |
| `row_index` | int | Row number in the source sheet, for tracing back to the file |
| `sheet_name` | string, nullable | |
| `raw_json` | text | The original row, verbatim, for audit/debugging |
| `account_name` | string, nullable | Proposed (fuzzy-matched) or user-confirmed account |
| `raw_scheme_name` | string, nullable | |
| `resolved_scheme_code` | string, nullable | `NULL` until mapped |
| `transaction_date`, `type`, `amount`, `nav`, `units`, `folio_no` | — | Parsed transaction fields |
| `source_hash` | string, nullable | Precomputed once the account is resolved, for early dedupe |
| `action` | string | `NEW` \| `DUPLICATE` \| `UNMAPPED` \| `ERROR` |
| `error` | string, nullable | Set when the row couldn't be parsed or committed |

**CRUD:** `POST /api/imports` (upload+parse), `GET /api/imports/{id}` and
`GET /api/imports/{id}/rows` (preview), `POST /api/imports/{id}/mappings/scheme` and
`.../mappings/account` (resolve), `POST /api/imports/{id}/commit` (write to `transactions`). Full
flow in [API.md](API.md#imports).

---

## Cross-cutting behavior

### Commission

Every transaction is entered as quantity, NAV, and the final amount that moved at the bank.
Commission is *derived*, never entered directly, and the formula's direction flips:

| Type | Relationship | Derivation |
|---|---|---|
| PURCHASE / SIP | `amount = (nav × units) + commission` | `commission = amount − (nav × units)` |
| REDEMPTION | `amount = (nav × units) − commission` | `commission = (nav × units) − amount` |

On a purchase you pay charges *on top of* what reaches the fund; on a redemption, charges are
taken *out of* the proceeds before the money reaches you. Commission must be ≥ 0 in both
directions - a negative result means a mistyped NAV, units, or amount, and manual/SIP entry reject
it outright (`services/charges.py::InvalidCommissionError`). The importer alone accepts a small
±₹1 tolerance for paise-level rounding noise already baked into historical statement data (see
`services/imports.py::_IMPORT_COMMISSION_TOLERANCE`) - real typos are orders of magnitude
larger than that and still get rejected.

### Derived, never stored

Realized gain, FIFO lot cost/avg cost NAV, and XIRR are **never** written to the database - they're
recomputed from the `transactions` table on every dashboard/holdings request
(`services/fifo.py`, `services/xirr.py`, `services/portfolio.py`). Storing them would
go stale the instant an earlier transaction is edited or soft-deleted; recomputing costs
microseconds at this data volume.

Same rule for the dashboard's day-wise portfolio-value series
(`services/portfolio_history.py::compute_portfolio_value_history`, backing
`GET /api/dashboard/history`): only its raw *input* - daily NAV history - is persisted (see
`scheme_nav_history` above); the aggregated series itself is swept fresh from that table plus
`transactions` on every request, never cached, for the same staleness reason.

### SIP execution model

`sips` describes a mandate; `transactions` (with `source = SIP`) records what actually happened.
Nothing bridges the two automatically. `services/sip_schedule.py::generate_schedule` is a pure
function that projects every occurrence a mandate implies, up to some date, adjusted for weekends
and the `market_holidays` calendar. `services/sips.py::due_entries` diffs that projection
against confirmed transactions and `sip_skips` to find what still needs the user's input. A
transaction is written only via `confirm_entry`, once real NAV and units are supplied.
