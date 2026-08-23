import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, createAccount, listAccounts, updateAccount, type AccountInput } from '../lib/api';
import type { Account } from '../types/api';

const emptyForm: AccountInput = { account_name: '', platform: '' };

export default function Accounts() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<AccountInput>(emptyForm);
  const [editError, setEditError] = useState<string | null>(null);

  const { data: accounts = [], isLoading } = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['accounts'] });

  const create = useMutation({
    mutationFn: (input: AccountInput) => createAccount(input),
    onSuccess: () => {
      setForm(emptyForm);
      setFormError(null);
      invalidate();
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Something went wrong.'),
  });

  const saveEdit = useMutation({
    mutationFn: (vars: { id: number; input: AccountInput }) => updateAccount(vars.id, vars.input),
    onSuccess: () => {
      setEditingId(null);
      setEditError(null);
      invalidate();
    },
    onError: (err) => setEditError(err instanceof ApiError ? err.message : 'Could not save changes.'),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.account_name.trim() || !form.platform.trim()) {
      setFormError('Fill in both account name and platform.');
      return;
    }
    create.mutate(form);
  }

  function startEdit(a: Account) {
    setEditingId(a.id);
    setEditError(null);
    setEditDraft({ account_name: a.account_name, platform: a.platform });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError(null);
  }

  function commitEdit(id: number) {
    if (!editDraft.account_name.trim() || !editDraft.platform.trim()) {
      setEditError('Fill in both account name and platform.');
      return;
    }
    saveEdit.mutate({ id, input: editDraft });
  }

  return (
    <div className="page">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Reference Data</p>
          <h2>Accounts</h2>
          <p className="hero-copy">
            Every transaction, SIP, and import belongs to one of these accounts - typically one per
            brokerage/RTA relationship (e.g. "ICICI Direct - Ashu"). Renaming one here updates it
            everywhere it's referenced; nothing else needs to change.
          </p>
        </div>
      </section>

      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Add</p>
            <h3>New account</h3>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <table className="form-table">
            <tbody>
              <tr>
                <td className="form-table__label">Account name</td>
                <td>
                  <input
                    type="text"
                    placeholder="e.g. ICICI Direct - Ashu"
                    value={form.account_name}
                    onChange={(e) => setForm((f) => ({ ...f, account_name: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Platform</td>
                <td>
                  <input
                    type="text"
                    placeholder="e.g. ICICI Direct"
                    value={form.platform}
                    onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value }))}
                  />
                </td>
              </tr>
              <tr>
                <td></td>
                <td className="form-table__actions">
                  <button className="btn btn--primary" type="submit" disabled={create.isPending}>
                    {create.isPending ? 'Saving…' : 'Add account'}
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
            <p className="eyebrow">All accounts</p>
            <h3>{accounts.length}</h3>
          </div>
        </div>
        {isLoading ? (
          <p className="empty-state">Loading…</p>
        ) : accounts.length === 0 ? (
          <p className="empty-state">No accounts yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account name</th>
                  <th>Platform</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) =>
                  editingId === a.id ? (
                    <tr key={a.id} className="row--editing">
                      <td>
                        <input
                          type="text"
                          className="due-table__input"
                          value={editDraft.account_name}
                          onChange={(e) => setEditDraft((d) => ({ ...d, account_name: e.target.value }))}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          className="due-table__input"
                          value={editDraft.platform}
                          onChange={(e) => setEditDraft((d) => ({ ...d, platform: e.target.value }))}
                        />
                      </td>
                      <td className="due-table__actions">
                        <button
                          className="btn btn--small btn--primary"
                          onClick={() => commitEdit(a.id)}
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
                    <tr key={a.id}>
                      <td>{a.account_name}</td>
                      <td>{a.platform}</td>
                      <td className="due-table__actions">
                        <button className="btn btn--small" onClick={() => startEdit(a)}>
                          Edit
                        </button>
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
