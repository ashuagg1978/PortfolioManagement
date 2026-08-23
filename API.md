# API Reference

FastAPI backend. Interactive docs (generated from the same code, always current) are served at
`http://localhost:8000/docs` when the backend is running. This file is the narrative version - what
each endpoint is for and how the pieces fit together; see [DATABASE.md](DATABASE.md) for the
schema each one reads or writes.

All routes below are prefixed with `/api` except `/health`. All money/NAV/units fields are plain
JSON numbers (not strings) - see [DATABASE.md](DATABASE.md#money-nav-and-units-are-stored-as-text-not-float).

## Authentication

None yet. Every route resolves the single seeded user via `api/deps.py::get_current_user`
(matched by `SEED_USER_EMAIL`), and every query is already scoped by that user's `user_id` -
directly, or indirectly through `account_id`/`sip_id`/`batch_id` ownership checks. Adding real auth
later means changing the body of that one dependency function; no route needs to change.

## Errors

Standard FastAPI/Pydantic shape: `{"detail": "..."}`.

| Status | Meaning |
|---|---|
| `404` | The referenced account/transaction/SIP/batch doesn't exist or isn't owned by this user |
| `422` | Validation failure - a negative derived commission, an over-redemption, an unknown scheme code, a batch already committed, etc. `detail` is a human-readable message naming the likely mistake, not a generic Pydantic dump |

---

## Health

### `GET /health`
`{"status": "ok"}`. No auth, no DB access - just confirms the process is up.

---

## Accounts

### `GET /api/accounts`
Lists the current user's accounts. → `AccountOut[]` (`id`, `account_name`, `platform`).

### `POST /api/accounts`
Body: `{account_name, platform}`. Creates a new account. → `AccountOut`, `201`. `422` if an account
with that name already exists (unique per user).

### `PATCH /api/accounts/{id}`
Body: `{account_name, platform}`. Renames the account and/or changes its platform label - every
transaction/SIP/import already referencing it by id is unaffected. → `AccountOut`. `422` on a name
collision, `404` if the account doesn't exist or isn't the current user's.

---

## NAV / Schemes

### `POST /api/nav/sync`
**The "Sync NAV" button - the only way NAVs ever refresh.** No cron, no background job; a plain
on-demand POST that fetches the full AMFI `NAVAll.txt` feed (~1.5MB, ~14,000 schemes), parses it,
and bulk-upserts every row into `schemes`.

Response:
```json
{
  "rows_parsed": 14288,
  "rows_upserted": 14288,
  "rows_skipped": 3,
  "feed_date": "2026-08-20",
  "duration_ms": 3874
}
```
`rows_skipped` counts rows the parser couldn't use (a handful of dead/stale schemes carry `N.A.`
instead of a NAV) - not an error, just excluded from the upsert.

### `GET /api/schemes/search?q=&limit=20`
Typeahead used by every scheme picker in the UI - searches scheme name (case-insensitive) and
scheme code. Returns `[]` for queries under 2 characters (not a 422 - the frontend calls this on
every keystroke). → `SchemeSearchResult[]` (`scheme_code`, `scheme_name`, `plan`, `option`,
`latest_nav`, `nav_date`).

### `GET /api/schemes/{scheme_code}/nav-history?on=YYYY-MM-DD`
A convenience prefill for entering a **past** transaction (SIP confirmation, or a backdated manual
entry) - the AMFI feed (`POST /api/nav/sync`) only ever has *today's* NAV, so it has nothing to
offer for a historical date. Sourced from the community [mfapi.in](https://api.mfapi.in) historical-
NAV API instead - **not authoritative**, purely a starting point the user reviews and can overwrite
before confirming; nothing from this endpoint is ever written to the ledger on its own.

Returns the scheme's NAV on `on`, or the closest trading day before it (within a 10-day lookback,
to ride out a holiday cluster without silently reaching into an unrelated month) -
`{"nav": 122.7014, "nav_date": "2024-06-14"}`. → `null` (not a 404) when nothing is found - an
unknown scheme code, a network failure, or no data in range are all treated as "couldn't prefill
this", not an error, so the frontend just falls back to asking the user to enter it manually.

`services/nav_history.py` fetches the scheme's **entire** history and matches the date in Python -
mfapi.in's own documented `startDate`/`endDate` query params were verified live and do **not**
actually filter the response.

---

## Transactions

### `GET /api/transactions`
The ledger page's search/filter/pagination endpoint. Query params:

| Param | Meaning |
|---|---|
| `account_id` | Exact match |
| `scheme_code` | Exact match |
| `scheme_name` | Free text - matches the AMFI scheme name, the user's own display name (`portfolio_schemes`), **or** the scheme code itself, so one search box covers "type a fund name" and "paste a code" alike |
| `type` | `PURCHASE` \| `REDEMPTION` |
| `source` | `MANUAL` \| `SIP` \| `IMPORT` |
| `date_from`, `date_to` | Inclusive range |
| `include_deleted` | Default `false` |
| `limit`, `offset` | Default `limit=50` |

→ `TransactionListOut`: `{items: TransactionOut[], total: int}`, newest first. `total` is the count
matching every filter *except* `limit`/`offset`, for building pagination controls. Every
`TransactionOut` here (and from every other transaction-returning route below) is enriched with
`account_name` and `scheme_display_name` - resolved per unique account/scheme in the page, not per
row, so this stays cheap even at the page size limit.

### `POST /api/transactions`
Body:
```json
{
  "account_id": 1, "scheme_code": "103196", "transaction_date": "2024-01-15",
  "type": "PURCHASE", "nav": 120.5, "units": 41.5, "amount": 5010.75,
  "folio_no": null
}
```
Derives `commission` and `signed_amount` server-side (see
[DATABASE.md#commission](DATABASE.md#commission)); on `REDEMPTION`, validates that enough units
are actually held in that account/scheme/folio as of the transaction date before allowing it. If a
transaction with these exact details was previously soft-deleted, it's **restored** instead of
rejected as a duplicate (see [DATABASE.md](DATABASE.md#transactions)).
→ `TransactionOut`, `201`. `422` on invalid commission, over-redemption, or a genuine (active,
non-deleted) duplicate.

### `GET /api/transactions/export`
The same filters as `GET /api/transactions` above (everything except `limit`/`offset` - export
always covers the full filtered result set, not just whatever page the ledger happens to be
showing), returned as a `.xlsx` download instead of JSON. Columns: `Date | Account | Scheme |
Scheme Code | Type | Source | NAV | Units | Amount | Commission | Folio`, chronological ascending
(oldest first) - the opposite of the ledger's newest-first view, since a spreadsheet export reads
more naturally as a running history. → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

### `PATCH /api/transactions/{id}`
Body: `{transaction_date, nav, units, amount, folio_no}`. Re-derives commission and re-validates
redemption units, excluding this transaction itself from the "units already held" calculation.
→ `TransactionOut`.

### `DELETE /api/transactions/{id}`
**Soft delete** - sets `is_deleted = true`. Never removes the row. → `TransactionOut` (the
now-deleted record).

### `POST /api/transactions/{id}/restore`
Clears `is_deleted`. → `TransactionOut`.

### `POST /api/transactions/preview-commission`
Body: `{type, nav, units, amount}`. Stateless - no transaction is created or looked up. Lets the
transaction form show the server's authoritative commission figure live, without duplicating the
derivation rule in TypeScript. → `{commission, gross}`. `422` if the inputs imply negative
commission.

---

## Dashboard

### `GET /api/dashboard`
The portfolio-wide KPI rollup plus every scheme's holding row, computed fresh from the transaction
ledger on every call (nothing here is cached or pre-aggregated - see
[DATABASE.md#derived-never-stored](DATABASE.md#derived-never-stored)).

```json
{
  "net_invested": 63000.0, "current_value": 64582.48, "net_gain_loss": 1582.48,
  "total_return_pct": 2.51, "active_schemes": 1, "total_commission_paid": 20.0,
  "portfolio_xirr": 0.0435, "nav_as_of": "2026-08-20",
  "holdings": [ /* SchemeHoldingOut[] */ ]
}
```
- `net_invested` is the **FIFO cost basis of units still held** (`SchemeHoldingOut.net_invested`
  summed across schemes) - what you actually paid for what you're still holding, independent of
  today's market value. An earlier version computed this as `current_value − Σ signed_amount`,
  which for any scheme with no redemptions silently added `current_value` on top of the real
  invested amount (a $63,000 purchase-only holding worth $64,582 today showed "Net Invested:
  $127,582" - see `services/portfolio.py::compute_holdings` for the fix and why).
- `net_gain_loss` is the sum of every scheme's own `total_gain` (unrealized + realized) - kept
  consistent with what the per-scheme breakdown table shows, including realized gains from past
  redemptions.
- `nav_as_of` is `max(nav_date)` over **currently held** schemes only, not the global feed date -
  a fully-redeemed scheme's stale NAV date shouldn't move this banner.
- `portfolio_xirr` concatenates every scheme's cash flows plus **one** synthetic
  "sell everything today" flow (not one per scheme) - see
  [DATABASE.md](DATABASE.md#derived-never-stored) and `services/xirr.py`. `null` when it can't
  be solved (fewer than 2 flows, no sign change, all-same-date, solver non-convergence) - render
  this as "—", not "0%".

### `GET /api/dashboard/holdings`
Just the `holdings` array from above, as its own endpoint. Each `SchemeHoldingOut`:

| Field | Meaning |
|---|---|
| `net_units`, `net_invested`, `avg_cost_nav` | From FIFO lot accounting over active transactions |
| `latest_nav`, `nav_date`, `nav_source` | `nav_source` is `"NAVAll"` (fresh from the feed), `"Last txn NAV"` (feed has no row for this code - falls back to the most recent transaction's NAV), or `"Redeemed"` (no NAV available at all) |
| `current_value`, `unrealized_gain`, `realized_gain`, `total_gain`, `pct_gain` | |
| `status` | `"In Profit"` \| `"In Loss"` \| `"Flat"` \| `"Redeemed"` (units held = 0) |
| `xirr` | Scheme-level, `null` if unsolvable |

---

## SIPs

See [DATABASE.md#sip-execution-model](DATABASE.md#sip-execution-model) for the design; this is the
HTTP surface over it. Every `SipOut` below is enriched with `account_name` and `scheme_display_name`,
the same way `TransactionOut` is (see [Transactions](#transactions) above).

### `GET /api/sips?active_only=true`
→ `SipOut[]`.

### `POST /api/sips`
Body: `{account_id, scheme_code, amount, frequency, start_date, end_date?, folio_no?}`.
`frequency` is `"MONTHLY"` or `"BIWEEKLY"`; omit `end_date` for a perpetual SIP. → `SipOut`, `201`.

### `POST /api/sips/{id}/version`
The "close and clone" edit flow. Body: `{effective_date, amount?, frequency?, folio_no?}` - only
the fields being changed need to be supplied; omitted fields carry over from the current SIP. Closes
the existing row (`end_date = effective_date - 1 day`, `is_active = false`) and creates a new one
starting `effective_date`, linked via `parent_sip_id`. → `SipOut` (the new row). Works regardless of
whether the SIP being edited is currently active, held, or stopped - the new row is always active,
so this doubles as "resume with different terms."

### `POST /api/sips/{id}/hold`
Pauses a SIP (`is_active = false`, `end_date` untouched) - no new due entries or upcoming
projections while held, since both already filter on `is_active`. The mandate's own terms are not
touched, so `POST /api/sips/{id}/resume` brings it back exactly as it was. → `SipOut`.

### `POST /api/sips/{id}/resume`
Reactivates a held or stopped SIP - **always clears `end_date`**, so resuming something that was
stopped doesn't reactivate it into a state with no future occurrences at all (`start_date >
end_date` produces an empty schedule, which would look identical to still being paused). → `SipOut`.

### `POST /api/sips/{id}/stop`
Body: `{end_date?}` - defaults to today. Permanently ends a SIP as of that date
(`is_active = false`, `end_date` set) - a direct mutation, not a close-and-clone, since there's no
successor row: the mandate's own `start_date`/`end_date` is the historical record of when it ran.
`422` if `end_date` is before the SIP's `start_date`. → `SipOut`.

### `GET /api/sips/due`
**The core read of the SIP Entries Due page.** For every active SIP, projects occurrences from
`start_date` through today, adjusted for weekends/holidays, and returns every one that doesn't yet
have a matching transaction or `sip_skips` row.
```json
[{
  "sip_id": 1, "account_id": 2, "account_name": "Maniqm - Ashu",
  "scheme_code": "103196", "display_name": "Nippon India ELSS Tax Saver Fund",
  "scheduled_date": "2025-01-31", "adjusted_date": "2025-01-31",
  "expected_amount": 5000.0, "folio_no": null, "calendar_complete": true
}]
```
- `scheduled_date` is the raw, unadjusted date and is what gets echoed back to `confirm`/`skip`
  (it's the idempotency key - see [DATABASE.md](DATABASE.md#transactions)).
- `adjusted_date` is what to show as "due on" - already rolled forward past weekends/holidays.
- `calendar_complete: false` means this occurrence's year has no seeded holiday data, so only
  weekend adjustment was applied - the UI shows an "uncertain date" badge in that case.

### `GET /api/sips/due/count`
`{"count": 17}` - powers the nav-bar badge. Polled every 60s by the frontend.

### `POST /api/sips/due/confirm`
Body: `{sip_id, scheduled_date, transaction_date?, nav, units}`. `amount` is **not** supplied - it's
locked from the SIP mandate. By default uses the trading-day-adjusted date the system computed
(same as `due`'s `adjusted_date`); pass `transaction_date` to override it with whatever the user's
actual statement shows instead - `scheduled_date` (the idempotency key) is untouched either way, so
overriding the date can never create a duplicate or break re-confirm idempotency. Derives commission
the same way any purchase does, and writes a `transactions` row with `source = SIP`. **Idempotent**:
confirming the same `(sip_id, scheduled_date)` twice returns the existing transaction rather than
erroring or duplicating. → `TransactionOut`.

### `POST /api/sips/due/skip`
Body: `{sip_id, scheduled_date, reason?}`. Records the occurrence as never-executed so it stops
appearing in `due` without a fabricated transaction. → `{id, sip_id, scheduled_date}`.

### `GET /api/sips/upcoming?n=5`
Read-only projection of the next `n` occurrences per active SIP, strictly in the future - **never**
written anywhere. → `UpcomingOccurrenceOut[]`.

---

## Imports

Three-step, stateless-safe pipeline: **upload** (parse + stage) → **resolve** (map anything
ambiguous) → **commit** (write to `transactions`). See
[DATABASE.md#import_batches--import_rows](DATABASE.md#import_batches--import_rows) for why parsed
rows are persisted rather than held in memory between steps.

### `POST /api/imports` (multipart, field name `file`)
Parses every `Txn-*` sheet in the uploaded workbook (tolerant header detection - column position
isn't hardcoded, since that's exactly how the workbook's own AMFI NAV lookup broke), plus its
`Scheme Map` and `NAV Reference` sheets (seeded immediately as global `scheme_aliases` /
`portfolio_schemes` - see [DATABASE.md](DATABASE.md#scheme_aliases)). Each row is staged with an
`action`:

| Action | Meaning |
|---|---|
| `NEW` | Parsed cleanly, scheme resolved, ready to commit |
| `UNMAPPED` | Scheme name has no known alias - needs `mappings/scheme` |
| `DUPLICATE` | Matches an existing transaction's `source_hash` (detected early when the account already auto-resolved; also re-checked at commit) |
| `ERROR` | Couldn't be parsed at all (missing date/amount/units/NAV, unclassifiable type) |

→ `ImportBatchOut`, `201`:
```json
{
  "id": 1, "filename": "MFs Portfolio Dashboard.xlsx", "status": "PENDING",
  "row_count": 632, "action_counts": {"NEW": 613, "UNMAPPED": 18, "ERROR": 1},
  "unmapped_scheme_names": ["..."], "unresolved_sheet_names": [],
  "accounts_available": [{"id": 1, "account_name": "ICICI Direct - Ashu"}]
}
```
`unresolved_sheet_names` lists any `Txn-*` sheet whose name couldn't be fuzzy-matched to an
existing account (e.g. "ICICI Ashu" → "ICICI Direct - Ashu" matches; something unrecognizable
won't) - resolve those via `mappings/account` before committing.

### `GET /api/imports/{batch_id}`
Same `ImportBatchOut` shape, for returning to an in-progress batch later without re-uploading.

### `GET /api/imports/{batch_id}/rows?action=&limit=200&offset=0`
The individual staged rows, optionally filtered by `action`. → `ImportRowOut[]`.

### `POST /api/imports/{batch_id}/mappings/scheme`
Body: `{raw_name, scheme_code}`. Records a `scheme_aliases` row for future imports too, and
re-resolves every `UNMAPPED` row in this batch with that `raw_name` to `NEW`. → `ImportBatchOut`
(updated counts).

### `POST /api/imports/{batch_id}/mappings/account`
Body: `{sheet_name, account_id}`. Assigns every row from that sheet to the chosen account.
→ `ImportBatchOut`.

### `POST /api/imports/{batch_id}/commit`
Writes every `NEW` row as a real transaction (chronological order, so a redemption is never
processed before an earlier purchase that happens to appear later in the sheet - avoids a spurious
over-redemption rejection). Rows that turn out to collide with an existing transaction at commit
time flip to `DUPLICATE` rather than failing the batch; rows still missing a resolved
account/scheme are counted `unresolved` and left uncommitted. `422` if the batch was already
committed.
```json
{"committed": 619, "duplicates": 1, "unresolved": 10, "errors": 2}
```
