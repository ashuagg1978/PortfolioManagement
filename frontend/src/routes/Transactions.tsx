import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiError,
  createTransaction,
  listAccounts,
  listTransactions,
  restoreTransaction,
  softDeleteTransaction,
  type TransactionInput,
} from '../lib/api';
import { formatCurrency, formatDate, formatNav, formatUnits } from '../lib/format';
import CommissionField from '../components/CommissionField';
import SchemeCodeField from '../components/SchemeCodeField';
import SchemeSearchInput from '../components/SchemeSearchInput';
import type { TransactionType } from '../types/api';

const emptyForm = {
  account_id: '',
  scheme_code: '',
  scheme_label: '',
  transaction_date: new Date().toISOString().slice(0, 10),
  type: 'PURCHASE' as TransactionType,
  nav: '',
  units: '',
  amount: '',
  folio_no: '',
};

export default function Transactions() {
  const queryClient = useQueryClient();
  const [showDeleted, setShowDeleted] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });
  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ['transactions', showDeleted],
    queryFn: () => listTransactions({ include_deleted: showDeleted }),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['transactions'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const create = useMutation({
    mutationFn: (input: TransactionInput) => createTransaction(input),
    onSuccess: () => {
      setForm(emptyForm);
      setFormError(null);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Something went wrong.'),
  });

  const softDelete = useMutation({ mutationFn: softDeleteTransaction, onSuccess: invalidate });
  const restore = useMutation({ mutationFn: restoreTransaction, onSuccess: invalidate });

  const navNum = form.nav ? Number(form.nav) : null;
  const unitsNum = form.units ? Number(form.units) : null;
  const amountNum = form.amount ? Number(form.amount) : null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.account_id || !form.scheme_code || navNum === null || unitsNum === null || amountNum === null) {
      setFormError('Fill in account, scheme, NAV, units and amount.');
      return;
    }
    create.mutate({
      account_id: Number(form.account_id),
      scheme_code: form.scheme_code,
      transaction_date: form.transaction_date,
      type: form.type,
      nav: navNum,
      units: unitsNum,
      amount: amountNum,
      folio_no: form.folio_no || null,
    });
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Ledger</p>
            <h3>Add transaction</h3>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <table className="form-table">
            <tbody>
              <tr>
                <td className="form-table__label">Account</td>
                <td>
                  <select
                    value={form.account_id}
                    onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
                  >
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
                <td className="form-table__label">Type</td>
                <td>
                  <select
                    value={form.type}
                    onChange={(e) => setForm((f) => ({ ...f, type: e.target.value as TransactionType }))}
                  >
                    <option value="PURCHASE">Purchase</option>
                    <option value="REDEMPTION">Redemption</option>
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
                <td className="form-table__label">Date</td>
                <td>
                  <input
                    type="date"
                    value={form.transaction_date}
                    onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">NAV</td>
                <td>
                  <input
                    type="number"
                    step="0.0001"
                    value={form.nav}
                    onChange={(e) => setForm((f) => ({ ...f, nav: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Units</td>
                <td>
                  <input
                    type="number"
                    step="0.001"
                    value={form.units}
                    onChange={(e) => setForm((f) => ({ ...f, units: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Amount ({form.type === 'PURCHASE' ? 'debited' : 'credited'})</td>
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
                <td className="form-table__label">Commission</td>
                <td>
                  <CommissionField type={form.type} nav={navNum} units={unitsNum} amount={amountNum} />
                </td>
              </tr>
              <tr>
                <td></td>
                <td className="form-table__actions">
                  <button className="btn btn--primary" type="submit" disabled={create.isPending}>
                    {create.isPending ? 'Saving…' : 'Add transaction'}
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
            <p className="eyebrow">History</p>
            <h3>All transactions</h3>
          </div>
          <label className="toggle">
            <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
            Show deleted
          </label>
        </div>

        {isLoading ? (
          <p className="empty-state">Loading…</p>
        ) : transactions.length === 0 ? (
          <p className="empty-state">No transactions yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Scheme</th>
                  <th>Type</th>
                  <th>Source</th>
                  <th>NAV</th>
                  <th>Units</th>
                  <th>Amount</th>
                  <th>Commission</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className={t.is_deleted ? 'row--deleted' : ''}>
                    <td>{formatDate(t.transaction_date)}</td>
                    <td>{t.scheme_code}</td>
                    <td>
                      <span className={t.type === 'PURCHASE' ? 'positive' : 'negative'}>{t.type}</span>
                    </td>
                    <td>{t.source}</td>
                    <td>{formatNav(t.nav)}</td>
                    <td>{formatUnits(t.units)}</td>
                    <td>{formatCurrency(t.amount)}</td>
                    <td>{formatCurrency(t.commission)}</td>
                    <td>
                      {t.is_deleted ? (
                        <button className="btn btn--small" onClick={() => restore.mutate(t.id)}>
                          Restore
                        </button>
                      ) : (
                        <button className="btn btn--small btn--danger" onClick={() => softDelete.mutate(t.id)}>
                          Delete
                        </button>
                      )}
                    </td>
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
