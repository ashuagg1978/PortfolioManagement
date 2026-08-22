import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, createSip, listAccounts, listSips, type SipInput } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/format';
import SchemeCodeField from '../components/SchemeCodeField';
import SchemeSearchInput from '../components/SchemeSearchInput';
import type { SipFrequency } from '../types/api';

const emptyForm = {
  account_id: '',
  scheme_code: '',
  scheme_label: '',
  amount: '',
  frequency: 'MONTHLY' as SipFrequency,
  start_date: new Date().toISOString().slice(0, 10),
  end_date: '',
  folio_no: '',
};

export default function Sips() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });
  const { data: sips = [], isLoading } = useQuery({ queryKey: ['sips'], queryFn: () => listSips(true) });

  const create = useMutation({
    mutationFn: (input: SipInput) => createSip(input),
    onSuccess: () => {
      setForm(emptyForm);
      setFormError(null);
      queryClient.invalidateQueries({ queryKey: ['sips'] });
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Something went wrong.'),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.account_id || !form.scheme_code || !form.amount) {
      setFormError('Fill in account, scheme and amount.');
      return;
    }
    create.mutate({
      account_id: Number(form.account_id),
      scheme_code: form.scheme_code,
      amount: Number(form.amount),
      frequency: form.frequency,
      start_date: form.start_date,
      end_date: form.end_date || null,
      folio_no: form.folio_no || null,
    });
  }

  const accountName = (id: number) => accounts.find((a) => a.id === id)?.account_name ?? id;

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">SIP mandate</p>
            <h3>Set up a SIP</h3>
          </div>
        </div>
        <p className="hint">
          Nothing is entered into the ledger automatically - occurrences appear on the{' '}
          <strong>Entries Due</strong> page once their date arrives, where you confirm the actual NAV and
          units from your statement.
        </p>
        <form onSubmit={handleSubmit}>
          <table className="form-table">
            <tbody>
              <tr>
                <td className="form-table__label">Account</td>
                <td>
                  <select value={form.account_id} onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}>
                    <option value="">Select…</option>
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.account_name}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Scheme</td>
                <td className="form-table__relative">
                  <SchemeSearchInput
                    value={form.scheme_code}
                    onSelect={(s) => setForm((f) => ({ ...f, scheme_code: s.scheme_code, scheme_label: s.scheme_name }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Scheme Code</td>
                <td>
                  <SchemeCodeField
                    code={form.scheme_code}
                    label={form.scheme_label}
                    onResolved={(s) => setForm((f) => ({ ...f, scheme_code: s.scheme_code, scheme_label: s.scheme_name }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Amount</td>
                <td>
                  <input
                    type="number"
                    step="0.01"
                    value={form.amount}
                    onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Frequency</td>
                <td>
                  <select
                    value={form.frequency}
                    onChange={(e) => setForm((f) => ({ ...f, frequency: e.target.value as SipFrequency }))}
                  >
                    <option value="MONTHLY">Monthly</option>
                    <option value="BIWEEKLY">Bi-weekly</option>
                  </select>
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Start date</td>
                <td>
                  <input
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">End date (optional - blank = perpetual)</td>
                <td>
                  <input
                    type="date"
                    value={form.end_date}
                    onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Folio No (optional)</td>
                <td>
                  <input
                    type="text"
                    value={form.folio_no}
                    onChange={(e) => setForm((f) => ({ ...f, folio_no: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td></td>
                <td className="form-table__actions">
                  <button className="btn btn--primary" type="submit" disabled={create.isPending}>
                    {create.isPending ? 'Saving…' : 'Create SIP'}
                  </button>
                  {formError && <p className="form-error">{formError}</p>}
                </td>
              </tr>
            </tbody>
          </table>
        </form>
      </section>

      <section className="panel panel--wide">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Active mandates</p>
            <h3>SIPs</h3>
          </div>
        </div>
        {isLoading ? (
          <p className="empty-state">Loading…</p>
        ) : sips.length === 0 ? (
          <p className="empty-state">No SIPs yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Scheme</th>
                  <th>Amount</th>
                  <th>Frequency</th>
                  <th>Start</th>
                  <th>End</th>
                </tr>
              </thead>
              <tbody>
                {sips.map((s) => (
                  <tr key={s.id}>
                    <td>{accountName(s.account_id)}</td>
                    <td>{s.scheme_code}</td>
                    <td>{formatCurrency(s.amount)}</td>
                    <td>{s.frequency}</td>
                    <td>{formatDate(s.start_date)}</td>
                    <td>{s.end_date ? formatDate(s.end_date) : 'Perpetual'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
