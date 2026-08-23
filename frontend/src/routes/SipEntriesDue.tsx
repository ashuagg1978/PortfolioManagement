import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, confirmDueEntry, getDueEntries, getNavOnDate, skipDueEntry } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/format';
import CommissionField from '../components/CommissionField';
import type { DueEntry } from '../types/api';

type RowKey = string; // `${sip_id}:${scheduled_date}`
const keyOf = (e: Pick<DueEntry, 'sip_id' | 'scheduled_date'>): RowKey => `${e.sip_id}:${e.scheduled_date}`;

interface RowState {
  date: string;
  nav: string;
  units: string;
  navTouched: boolean;
  unitsTouched: boolean;
}

function defaultRowState(entry: DueEntry): RowState {
  return { date: entry.adjusted_date, nav: '', units: '', navTouched: false, unitsTouched: false };
}

/** Renders nothing but a small status hint - fetches the historical NAV for
 * this row's (scheme, date) and reports it back to the parent, which owns
 * all the actual input state. Split out purely so each row can call its
 * own useQuery (one hook instance per row, via a real component instance -
 * not a hook call inside a .map(), which React disallows). */
function NavAutoFetch({
  schemeCode,
  date,
  navTouched,
  onFetched,
}: {
  schemeCode: string;
  date: string;
  navTouched: boolean;
  onFetched: (nav: string) => void;
}) {
  const { data, isFetching } = useQuery({
    queryKey: ['nav-history', schemeCode, date],
    queryFn: () => getNavOnDate(schemeCode, date),
    enabled: Boolean(date),
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (data && !navTouched) onFetched(String(data.nav));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, navTouched, date]);

  if (isFetching) return <p className="hint hint--inline">Fetching NAV…</p>;
  if (data === null && !navTouched) return <p className="hint hint--inline">No historical NAV found - enter manually.</p>;
  return null;
}

export default function SipEntriesDue() {
  const queryClient = useQueryClient();
  const { data: due = [], isLoading } = useQuery({ queryKey: ['sips', 'due'], queryFn: getDueEntries });

  const [inputs, setInputs] = useState<Record<RowKey, RowState>>({});
  const [rowErrors, setRowErrors] = useState<Record<RowKey, string>>({});

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['sips', 'due'] });
    queryClient.invalidateQueries({ queryKey: ['sips', 'due', 'count'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['transactions'] });
  };

  const confirm = useMutation({
    mutationFn: confirmDueEntry,
    onSuccess: (_data, variables) => {
      setRowErrors((r) => ({ ...r, [`${variables.sip_id}:${variables.scheduled_date}`]: '' }));
      invalidate();
    },
    onError: (err, variables) => {
      const message = err instanceof ApiError ? err.message : 'Could not confirm this entry.';
      setRowErrors((r) => ({ ...r, [`${variables.sip_id}:${variables.scheduled_date}`]: message }));
    },
  });

  const skip = useMutation({ mutationFn: skipDueEntry, onSuccess: invalidate });

  function rowState(key: RowKey, entry: DueEntry): RowState {
    return inputs[key] ?? defaultRowState(entry);
  }

  function handleDateChange(entry: DueEntry, newDate: string) {
    const key = keyOf(entry);
    // A new date means a fresh NAV lookup, so both fields reset to "start over".
    setInputs((prev) => ({ ...prev, [key]: { ...defaultRowState(entry), date: newDate } }));
  }

  function handleNavChange(entry: DueEntry, value: string, fromUser: boolean) {
    const key = keyOf(entry);
    setInputs((prev) => {
      const row = rowState(key, entry);
      const navNum = Number(value);
      const recomputeUnits = navNum > 0 && !row.unitsTouched;
      return {
        ...prev,
        [key]: {
          ...row,
          nav: value,
          navTouched: fromUser ? true : row.navTouched,
          units: recomputeUnits ? (entry.expected_amount / navNum).toFixed(3) : row.units,
        },
      };
    });
  }

  function handleUnitsChange(entry: DueEntry, value: string) {
    const key = keyOf(entry);
    setInputs((prev) => ({ ...prev, [key]: { ...rowState(key, entry), units: value, unitsTouched: true } }));
  }

  function confirmRow(entry: DueEntry) {
    const key = keyOf(entry);
    const row = rowState(key, entry);
    const nav = Number(row.nav);
    const units = Number(row.units);
    if (!row.date || !nav || !units) {
      setRowErrors((r) => ({ ...r, [key]: 'Enter date, NAV and units.' }));
      return;
    }
    confirm.mutate({
      sip_id: entry.sip_id,
      scheduled_date: entry.scheduled_date,
      transaction_date: row.date,
      nav,
      units,
    });
  }

  function isReady(entry: DueEntry): boolean {
    const row = rowState(keyOf(entry), entry);
    const nav = Number(row.nav);
    const units = Number(row.units);
    if (!row.date || !(nav > 0) || !(units > 0)) return false;
    const gross = nav * units;
    return entry.expected_amount - gross >= -0.005;
  }

  function confirmAllValid() {
    for (const entry of due) {
      if (isReady(entry)) confirmRow(entry);
    }
  }

  const readyCount = due.filter(isReady).length;

  return (
    <div className="page">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">SIP execution</p>
          <h2>Entries due</h2>
          <p className="hero-copy">
            Nothing here is entered automatically - the AMFI feed only has today's NAV, so past SIP dates
            need the real NAV and units from your statement. NAV is pre-filled from historical data where
            available (and units from NAV + the mandate's fixed amount) - review and adjust the date, NAV
            or units before confirming. Confirm turns a row into a transaction; Skip marks it as never
            executed (bounced mandate, insufficient funds) without inventing a row.
          </p>
        </div>
        {readyCount > 0 && (
          <button className="btn btn--primary" onClick={confirmAllValid} disabled={confirm.isPending}>
            Confirm all ready ({readyCount})
          </button>
        )}
      </section>

      {isLoading ? (
        <p className="empty-state">Loading…</p>
      ) : due.length === 0 ? (
        <p className="empty-state">Nothing due - every SIP is up to date.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table due-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Scheme</th>
                <th>Date</th>
                <th>Expected amount</th>
                <th>NAV</th>
                <th>Units</th>
                <th>Commission</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {due.map((entry) => {
                const key = keyOf(entry);
                const row = rowState(key, entry);
                const navNum = row.nav ? Number(row.nav) : null;
                const unitsNum = row.units ? Number(row.units) : null;
                return (
                  <tr key={key}>
                    <td>{entry.account_name}</td>
                    <td>
                      {entry.display_name}
                      {!entry.calendar_complete && (
                        <span
                          className="badge badge--warn"
                          title="No holiday calendar data for this year - weekend-only adjustment was used"
                        >
                          uncertain date
                        </span>
                      )}
                    </td>
                    <td>
                      <input
                        type="date"
                        value={row.date}
                        onChange={(e) => handleDateChange(entry, e.target.value)}
                        className="due-table__input"
                      />
                      {row.date !== entry.adjusted_date && (
                        <p className="hint hint--inline">System suggested {formatDate(entry.adjusted_date)}</p>
                      )}
                    </td>
                    <td>{formatCurrency(entry.expected_amount)}</td>
                    <td>
                      <input
                        type="number"
                        step="0.0001"
                        value={row.nav}
                        onChange={(e) => handleNavChange(entry, e.target.value, true)}
                        className="due-table__input"
                      />
                      <NavAutoFetch
                        schemeCode={entry.scheme_code}
                        date={row.date}
                        navTouched={row.navTouched}
                        onFetched={(nav) => handleNavChange(entry, nav, false)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.001"
                        value={row.units}
                        onChange={(e) => handleUnitsChange(entry, e.target.value)}
                        className="due-table__input"
                      />
                    </td>
                    <td>
                      <CommissionField type="PURCHASE" nav={navNum} units={unitsNum} amount={entry.expected_amount} />
                    </td>
                    <td className="due-table__actions">
                      <button className="btn btn--small btn--primary" onClick={() => confirmRow(entry)} disabled={confirm.isPending}>
                        Confirm
                      </button>
                      <button
                        className="btn btn--small"
                        onClick={() => skip.mutate({ sip_id: entry.sip_id, scheduled_date: entry.scheduled_date })}
                        disabled={skip.isPending}
                      >
                        Skip
                      </button>
                      {rowErrors[key] && <p className="form-error form-error--inline">{rowErrors[key]}</p>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
