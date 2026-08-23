import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiError,
  createSip,
  holdSip,
  listAccounts,
  listSips,
  resumeSip,
  stopSip,
  versionSip,
  type SipInput,
} from '../lib/api';
import { formatCurrency, formatDate } from '../lib/format';
import SchemeCodeField from '../components/SchemeCodeField';
import SchemeSearchInput from '../components/SchemeSearchInput';
import type { Sip, SipFrequency } from '../types/api';

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

interface EditDraft {
  amount: string;
  frequency: SipFrequency;
  folio_no: string;
  effective_date: string;
}

function sipStatus(s: Sip): { label: string; tone: 'active' | 'held' | 'stopped' } {
  if (s.is_active) return { label: 'Active', tone: 'active' };
  return s.end_date ? { label: `Stopped ${formatDate(s.end_date)}`, tone: 'stopped' } : { label: 'Held', tone: 'held' };
}

export default function Sips() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft>({
    amount: '',
    frequency: 'MONTHLY',
    folio_no: '',
    effective_date: new Date().toISOString().slice(0, 10),
  });
  const [editError, setEditError] = useState<string | null>(null);

  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });
  const { data: sips = [], isLoading } = useQuery({
    queryKey: ['sips', showInactive],
    queryFn: () => listSips(!showInactive),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['sips'] });
    queryClient.invalidateQueries({ queryKey: ['sips', 'due'] });
    queryClient.invalidateQueries({ queryKey: ['sips', 'due', 'count'] });
    queryClient.invalidateQueries({ queryKey: ['sips', 'upcoming'] });
  };

  const create = useMutation({
    mutationFn: (input: SipInput) => createSip(input),
    onSuccess: () => {
      setForm(emptyForm);
      setFormError(null);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Something went wrong.'),
  });

  const hold = useMutation({ mutationFn: holdSip, onSuccess: invalidate });
  const resume = useMutation({ mutationFn: resumeSip, onSuccess: invalidate });
  const stop = useMutation({ mutationFn: (id: number) => stopSip(id), onSuccess: invalidate });

  const saveEdit = useMutation({
    mutationFn: (vars: { id: number; input: Parameters<typeof versionSip>[1] }) =>
      versionSip(vars.id, vars.input),
    onSuccess: () => {
      setEditingId(null);
      setEditError(null);
      invalidate();
    },
    onError: (err) => setEditError(err instanceof ApiError ? err.message : 'Could not save changes.'),
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

  function startEdit(s: Sip) {
    setEditingId(s.id);
    setEditError(null);
    setEditDraft({
      amount: String(s.amount),
      frequency: s.frequency,
      folio_no: s.folio_no ?? '',
      effective_date: new Date().toISOString().slice(0, 10),
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError(null);
  }

  function commitEdit(s: Sip) {
    const amount = Number(editDraft.amount);
    if (!amount || !editDraft.effective_date) {
      setEditError('Fill in amount and an effective date.');
      return;
    }
    saveEdit.mutate({
      id: s.id,
      input: {
        effective_date: editDraft.effective_date,
        amount,
        frequency: editDraft.frequency,
        folio_no: editDraft.folio_no || null,
      },
    });
  }

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
            <p className="eyebrow">Mandates</p>
            <h3>SIPs</h3>
          </div>
          <label className="toggle">
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            Show held / stopped
          </label>
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
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sips.map((s) =>
                  editingId === s.id ? (
                    <tr key={s.id} className="row--editing">
                      <td>{s.account_name}</td>
                      <td>{s.scheme_display_name}</td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          className="due-table__input"
                          value={editDraft.amount}
                          onChange={(e) => setEditDraft((d) => ({ ...d, amount: e.target.value }))}
                        />
                      </td>
                      <td>
                        <select
                          className="due-table__input"
                          value={editDraft.frequency}
                          onChange={(e) => setEditDraft((d) => ({ ...d, frequency: e.target.value as SipFrequency }))}
                        >
                          <option value="MONTHLY">Monthly</option>
                          <option value="BIWEEKLY">Bi-weekly</option>
                        </select>
                      </td>
                      <td colSpan={2}>
                        <label className="edit-inline-label">
                          Effective from
                          <input
                            type="date"
                            className="due-table__input"
                            value={editDraft.effective_date}
                            onChange={(e) => setEditDraft((d) => ({ ...d, effective_date: e.target.value }))}
                          />
                        </label>
                      </td>
                      <td>
                        <input
                          type="text"
                          className="due-table__input"
                          placeholder="Folio"
                          value={editDraft.folio_no}
                          onChange={(e) => setEditDraft((d) => ({ ...d, folio_no: e.target.value }))}
                        />
                      </td>
                      <td className="due-table__actions">
                        <button
                          className="btn btn--small btn--primary"
                          onClick={() => commitEdit(s)}
                          disabled={saveEdit.isPending}
                        >
                          Save
                        </button>
                        <button className="btn btn--small" onClick={cancelEdit}>
                          Cancel
                        </button>
                        {editError && <p className="form-error form-error--inline">{editError}</p>}
                      </td>
                    </tr>
                  ) : (
                    <tr key={s.id}>
                      <td>{s.account_name}</td>
                      <td>{s.scheme_display_name}</td>
                      <td>{formatCurrency(s.amount)}</td>
                      <td>{s.frequency}</td>
                      <td>{formatDate(s.start_date)}</td>
                      <td>{s.end_date ? formatDate(s.end_date) : 'Perpetual'}</td>
                      <td>
                        <span className={`status-pill status-pill--sip-${sipStatus(s).tone}`}>{sipStatus(s).label}</span>
                      </td>
                      <td className="due-table__actions">
                        <button className="btn btn--small" onClick={() => startEdit(s)}>
                          Edit
                        </button>
                        {s.is_active ? (
                          <>
                            <button className="btn btn--small" onClick={() => hold.mutate(s.id)} disabled={hold.isPending}>
                              Hold
                            </button>
                            <button
                              className="btn btn--small btn--danger"
                              onClick={() => stop.mutate(s.id)}
                              disabled={stop.isPending}
                            >
                              Stop
                            </button>
                          </>
                        ) : (
                          <button className="btn btn--small btn--primary" onClick={() => resume.mutate(s.id)} disabled={resume.isPending}>
                            Resume
                          </button>
                        )}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
