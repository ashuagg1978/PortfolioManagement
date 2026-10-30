import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, createUser, listUsers, updateUser } from '../lib/api';
import { useAuth } from '../lib/auth';

const emptyForm = { name: '', email: '', password: '', is_admin: false };

export default function Users() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const { data: users = [], isLoading } = useQuery({ queryKey: ['admin', 'users'], queryFn: listUsers });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
  const onError = (err: unknown) => setError(err instanceof ApiError ? err.message : 'Something went wrong.');

  const create = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      setForm(emptyForm);
      setError(null);
      invalidate();
    },
    onError,
  });

  const update = useMutation({
    mutationFn: ({ id, ...input }: { id: number; is_active?: boolean; password?: string }) => updateUser(id, input),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError,
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate({ ...form, name: form.name.trim(), email: form.email.trim() });
  }

  function resetPassword(id: number, email: string) {
    const password = window.prompt(`New password for ${email} (min 8 characters):`);
    if (password) update.mutate({ id, password });
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Admin</p>
            <h3>Add a user</h3>
          </div>
        </div>
        <form onSubmit={onSubmit}>
          <table className="form-table">
            <tbody>
              <tr>
                <td className="form-table__label">Name</td>
                <td>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Username</td>
                <td>
                  <input
                    value={form.email}
                    placeholder="email address"
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Password</td>
                <td>
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Admin</td>
                <td>
                  <input
                    type="checkbox"
                    checked={form.is_admin}
                    onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
                  />
                </td>
              </tr>
              <tr>
                <td />
                <td className="form-table__actions">
                  <button type="submit" className="btn btn--primary" disabled={create.isPending}>
                    Add user
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </form>
        {error && <p className="form-error">{error}</p>}
      </section>

      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Admin</p>
            <h3>Users</h3>
          </div>
        </div>
        {isLoading ? (
          <p className="empty-state">Loading…</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>{u.email}</td>
                  <td>{u.is_admin ? 'Admin' : 'User'}</td>
                  <td>{u.is_active ? 'Active' : 'Disabled'}</td>
                  <td>
                    <button type="button" className="btn btn--small" onClick={() => resetPassword(u.id, u.email)}>
                      Reset password
                    </button>{' '}
                    {u.id !== me?.id && (
                      <button
                        type="button"
                        className={`btn btn--small${u.is_active ? ' btn--danger' : ''}`}
                        onClick={() => update.mutate({ id: u.id, is_active: !u.is_active })}
                      >
                        {u.is_active ? 'Disable' : 'Enable'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
