import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, confirmDueEntry, getDueEntries, skipDueEntry } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/format';
import CommissionField from '../components/CommissionField';
import type { DueEntry } from '../types/api';

type RowKey = string; // `${sip_id}:${scheduled_date}`
const keyOf = (e: Pick<DueEntry, 'sip_id' | 'scheduled_date'>): RowKey => `${e.sip_id}:${e.scheduled_date}`;

export default function SipEntriesDue() {
  const queryClient = useQueryClient();
  const { data: due = [], isLoading } = useQuery({ queryKey: ['sips', 'due'], queryFn: getDueEntries });

  const [inputs, setInputs] = useState<Record<RowKey, { nav: string; units: string }>>({});
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

  function setInput(key: RowKey, field: 'nav' | 'units', value: string) {
    setInputs((prev) => ({ ...prev, [key]: { ...prev[key], [field]: value } }));
  }

  function confirmRow(entry: DueEntry) {
    const key = keyOf(entry);
    const nav = Number(inputs[key]?.nav);
    const units = Number(inputs[key]?.units);
    if (!nav || !units) {
      setRowErrors((r) => ({ ...r, [key]: 'Enter both NAV and units.' }));
      return;
    }
    confirm.mutate({ sip_id: entry.sip_id, scheduled_date: entry.scheduled_date, nav, units });
  }

  function confirmAllValid() {
    for (const entry of due) {
      const key = keyOf(entry);
      const nav = Number(inputs[key]?.nav);
      const units = Number(inputs[key]?.units);
      if (nav > 0 && units > 0) {
        const gross = nav * units;
        const commissionOk = entry.expected_amount - gross >= -0.005;
        if (commissionOk) {
          confirm.mutate({ sip_id: entry.sip_id, scheduled_date: entry.scheduled_date, nav, units });
        }
      }
    }
  }

  const readyCount = due.filter((e) => {
    const key = keyOf(e);
    const nav = Number(inputs[key]?.nav);
    const units = Number(inputs[key]?.units);
    return nav > 0 && units > 0;
  }).length;

  return (
    <div className="page">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">SIP execution</p>
          <h2>Entries due</h2>
          <p className="hero-copy">
            Nothing here is entered automatically - the AMFI feed only has today's NAV, so past SIP dates
            need the real NAV and units from your statement. Confirm turns a row into a transaction; Skip
            marks it as never executed (bounced mandate, insufficient funds) without inventing a row.
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
                <th>Due date</th>
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
                const nav = inputs[key]?.nav ?? '';
                const units = inputs[key]?.units ?? '';
                return (
                  <tr key={key}>
                    <td>{entry.account_name}</td>
                    <td>
                      {entry.display_name}
                      {!entry.calendar_complete && (
                        <span className="badge badge--warn" title="No holiday calendar data for this year - weekend-only adjustment was used">
                          uncertain date
                        </span>
                      )}
                    </td>
                    <td>{formatDate(entry.adjusted_date)}</td>
                    <td>{formatCurrency(entry.expected_amount)}</td>
                    <td>
                      <input
                        type="number"
                        step="0.0001"
                        value={nav}
                        onChange={(e) => setInput(key, 'nav', e.target.value)}
                        className="due-table__input"
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.001"
                        value={units}
                        onChange={(e) => setInput(key, 'units', e.target.value)}
                        className="due-table__input"
                      />
                    </td>
                    <td>
                      <CommissionField
                        type="PURCHASE"
                        nav={nav ? Number(nav) : null}
                        units={units ? Number(units) : null}
                        amount={entry.expected_amount}
                      />
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
