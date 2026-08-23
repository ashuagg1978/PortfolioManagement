import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiError,
  createTransaction,
  listAccounts,
  listTransactions,
  restoreTransaction,
  softDeleteTransaction,
  transactionsExportUrl,
  updateTransaction,
  type TransactionInput,
} from '../lib/api';
import { formatCurrency, formatDate, formatNav, formatUnits } from '../lib/format';
import CommissionField from '../components/CommissionField';
import SchemeCodeField from '../components/SchemeCodeField';
import SchemeSearchInput from '../components/SchemeSearchInput';
import type { Transaction, TransactionSource, TransactionType } from '../types/api';

const PAGE_SIZE = 25;

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

interface EditDraft {
  transaction_date: string;
  nav: string;
  units: string;
  amount: string;
  folio_no: string;
}

export default function Transactions() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft>({ transaction_date: '', nav: '', units: '', amount: '', folio_no: '' });
  const [editError, setEditError] = useState<string | null>(null);

  // Filters live in the URL - shareable/bookmarkable, and how the dashboard's
  // MF-wise breakdown links here pre-filtered to one scheme.
  const accountId = searchParams.get('account_id') ?? '';
  const schemeQuery = searchParams.get('scheme_name') ?? '';
  const [schemeQueryDraft, setSchemeQueryDraft] = useState(schemeQuery);
  const type = searchParams.get('type') ?? '';
  const source = searchParams.get('source') ?? '';
  const dateFrom = searchParams.get('date_from') ?? '';
  const dateTo = searchParams.get('date_to') ?? '';
  const includeDeleted = searchParams.get('include_deleted') === 'true';
  const page = Math.max(0, Number(searchParams.get('page') ?? '0') || 0);

  // Debounce the free-text scheme search before it hits the URL/query.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (schemeQueryDraft !== schemeQuery) setFilter('scheme_name', schemeQueryDraft);
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemeQueryDraft]);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('page');
    setSearchParams(next, { replace: true });
  }

  function setPage(p: number) {
    const next = new URLSearchParams(searchParams);
    if (p > 0) next.set('page', String(p));
    else next.delete('page');
    setSearchParams(next, { replace: true });
  }

  function clearFilters() {
    setSearchParams(new URLSearchParams(), { replace: true });
    setSchemeQueryDraft('');
  }

  const hasFilters = Boolean(accountId || schemeQuery || type || source || dateFrom || dateTo || includeDeleted);

  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });

  const listFilters = {
    account_id: accountId ? Number(accountId) : undefined,
    scheme_name: schemeQuery || undefined,
    type: (type || undefined) as TransactionType | undefined,
    source: (source || undefined) as TransactionSource | undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    include_deleted: includeDeleted,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };

  // Same filters as the list, minus pagination - export always covers the
  // full filtered set, not just the page on screen. Uses schemeQueryDraft
  // (not the debounced schemeQuery) so exporting right after typing
  // reflects what's actually in the box.
  const exportUrl = transactionsExportUrl({
    account_id: accountId ? Number(accountId) : undefined,
    scheme_name: schemeQueryDraft || undefined,
    type: (type || undefined) as TransactionType | undefined,
    source: (source || undefined) as TransactionSource | undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    include_deleted: includeDeleted,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['transactions', listFilters],
    queryFn: () => listTransactions(listFilters),
  });
  const transactions = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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

  const saveEdit = useMutation({
    mutationFn: (vars: { id: number; input: Parameters<typeof updateTransaction>[1] }) =>
      updateTransaction(vars.id, vars.input),
    onSuccess: () => {
      setEditingId(null);
      setEditError(null);
      invalidate();
    },
    onError: (err) => setEditError(err instanceof ApiError ? err.message : 'Could not save changes.'),
  });

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

  function startEdit(t: Transaction) {
    setEditingId(t.id);
    setEditError(null);
    setEditDraft({
      transaction_date: t.transaction_date,
      nav: String(t.nav),
      units: String(t.units),
      amount: String(t.amount),
      folio_no: t.folio_no ?? '',
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError(null);
  }

  function commitEdit(t: Transaction) {
    const nav = Number(editDraft.nav);
    const units = Number(editDraft.units);
    const amount = Number(editDraft.amount);
    if (!editDraft.transaction_date || !nav || !units || !amount) {
      setEditError('Fill in date, NAV, units and amount.');
      return;
    }
    saveEdit.mutate({
      id: t.id,
      input: {
        transaction_date: editDraft.transaction_date,
        nav,
        units,
        amount,
        folio_no: editDraft.folio_no || null,
      },
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
            <h3>
              All transactions {total > 0 && <span className="panel__count">({total})</span>}
            </h3>
          </div>
          {total > 0 && (
            <a className="btn" href={exportUrl} download>
              ⬇ Export to Excel
            </a>
          )}
        </div>

        <div className="filter-bar">
          <label>
            Account
            <select value={accountId} onChange={(e) => setFilter('account_id', e.target.value)}>
              <option value="">All accounts</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.account_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Scheme
            <input
              type="text"
              placeholder="Name or code…"
              value={schemeQueryDraft}
              onChange={(e) => setSchemeQueryDraft(e.target.value)}
            />
          </label>
          <label>
            Type
            <select value={type} onChange={(e) => setFilter('type', e.target.value)}>
              <option value="">All types</option>
              <option value="PURCHASE">Purchase</option>
              <option value="REDEMPTION">Redemption</option>
            </select>
          </label>
          <label>
            Source
            <select value={source} onChange={(e) => setFilter('source', e.target.value)}>
              <option value="">All sources</option>
              <option value="MANUAL">Manual</option>
              <option value="SIP">SIP</option>
              <option value="IMPORT">Import</option>
            </select>
          </label>
          <label>
            From
            <input type="date" value={dateFrom} onChange={(e) => setFilter('date_from', e.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={dateTo} onChange={(e) => setFilter('date_to', e.target.value)} />
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => setFilter('include_deleted', e.target.checked ? 'true' : '')}
            />
            Show deleted
          </label>
          {hasFilters && (
            <button type="button" className="btn btn--small" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>

        {isLoading ? (
          <p className="empty-state">Loading…</p>
        ) : transactions.length === 0 ? (
          <p className="empty-state">No transactions match these filters.</p>
        ) : (
          <>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Account</th>
                    <th>Scheme</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>NAV</th>
                    <th>Units</th>
                    <th>Amount</th>
                    <th>Commission</th>
                    <th>Folio</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t) =>
                    editingId === t.id ? (
                      <tr key={t.id} className="row--editing">
                        <td>
                          <input
                            type="date"
                            className="due-table__input"
                            value={editDraft.transaction_date}
                            onChange={(e) => setEditDraft((d) => ({ ...d, transaction_date: e.target.value }))}
                          />
                        </td>
                        <td>{t.account_name}</td>
                        <td>{t.scheme_display_name}</td>
                        <td>{t.type}</td>
                        <td>{t.source}</td>
                        <td>
                          <input
                            type="number"
                            step="0.0001"
                            className="due-table__input"
                            value={editDraft.nav}
                            onChange={(e) => setEditDraft((d) => ({ ...d, nav: e.target.value }))}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.001"
                            className="due-table__input"
                            value={editDraft.units}
                            onChange={(e) => setEditDraft((d) => ({ ...d, units: e.target.value }))}
                          />
                        </td>
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
                          <CommissionField
                            type={t.type}
                            nav={editDraft.nav ? Number(editDraft.nav) : null}
                            units={editDraft.units ? Number(editDraft.units) : null}
                            amount={editDraft.amount ? Number(editDraft.amount) : null}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="due-table__input"
                            value={editDraft.folio_no}
                            onChange={(e) => setEditDraft((d) => ({ ...d, folio_no: e.target.value }))}
                          />
                        </td>
                        <td className="due-table__actions">
                          <button
                            className="btn btn--small btn--primary"
                            onClick={() => commitEdit(t)}
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
                      <tr key={t.id} className={t.is_deleted ? 'row--deleted' : ''}>
                        <td>{formatDate(t.transaction_date)}</td>
                        <td>{t.account_name}</td>
                        <td>{t.scheme_display_name}</td>
                        <td>
                          <span className={t.type === 'PURCHASE' ? 'positive' : 'negative'}>{t.type}</span>
                        </td>
                        <td>{t.source}</td>
                        <td>{formatNav(t.nav)}</td>
                        <td>{formatUnits(t.units)}</td>
                        <td>{formatCurrency(t.amount)}</td>
                        <td>{formatCurrency(t.commission)}</td>
                        <td>{t.folio_no ?? '—'}</td>
                        <td className="due-table__actions">
                          {!t.is_deleted && (
                            <button className="btn btn--small" onClick={() => startEdit(t)}>
                              Edit
                            </button>
                          )}
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
                    ),
                  )}
                </tbody>
              </table>
            </div>

            <div className="pagination">
              <button className="btn btn--small" disabled={page === 0} onClick={() => setPage(page - 1)}>
                ← Prev
              </button>
              <span className="pagination__status">
                Page {page + 1} of {totalPages}
              </span>
              <button className="btn btn--small" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)}>
                Next →
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
