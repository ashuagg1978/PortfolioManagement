import { useState, type FormEvent } from 'react';
import { ApiError, changePassword } from '../lib/api';
import { useAuth } from '../lib/auth';

export default function ChangePassword() {
  const { user } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setDone(false);
    if (next !== confirm) {
      setError('New passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Signed in as {user?.email}</p>
            <h3>Change password</h3>
          </div>
        </div>
        <form onSubmit={onSubmit}>
          <table className="form-table">
            <tbody>
              <tr>
                <td className="form-table__label">Current</td>
                <td>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={current}
                    onChange={(e) => setCurrent(e.target.value)}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">New</td>
                <td>
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={next}
                    onChange={(e) => setNext(e.target.value)}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td className="form-table__label">Confirm</td>
                <td>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                  />
                </td>
              </tr>
              <tr>
                <td />
                <td className="form-table__actions">
                  <button type="submit" className="btn btn--primary" disabled={busy}>
                    Update password
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </form>
        {error && <p className="form-error">{error}</p>}
        {done && <p className="hint">Password updated.</p>}
      </section>
    </div>
  );
}
