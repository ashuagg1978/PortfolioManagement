import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AccountHoldings } from '../types/api';
import { formatCurrency, formatNav, formatPercent, formatUnits, formatXirr } from '../lib/format';

export default function AccountBreakdown({ accounts }: { accounts: AccountHoldings[] }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set(accounts.map((a) => a.account_id)));

  if (accounts.length === 0) {
    return <p className="empty-state">No holdings yet - add a transaction or import your statement.</p>;
  }

  function toggle(accountId: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(accountId)) next.delete(accountId);
      else next.add(accountId);
      return next;
    });
  }

  return (
    <div className="account-breakdown">
      {accounts.map((account) => {
        const isOpen = expanded.has(account.account_id);
        return (
          <div key={account.account_id} className="account-group">
            <button
              type="button"
              className="account-group__header"
              onClick={() => toggle(account.account_id)}
              aria-expanded={isOpen}
            >
              <span className="account-group__chevron">{isOpen ? '▾' : '▸'}</span>
              <span className="account-group__name">{account.account_name}</span>
              <span className="account-group__stat">
                <span className="account-group__stat-label">Invested</span>
                {formatCurrency(account.net_invested)}
              </span>
              <span className="account-group__stat">
                <span className="account-group__stat-label">Current</span>
                {formatCurrency(account.current_value)}
              </span>
              <span className={`account-group__stat ${account.net_gain_loss >= 0 ? 'positive' : 'negative'}`}>
                <span className="account-group__stat-label">Gain/Loss</span>
                {formatCurrency(account.net_gain_loss)} ({formatPercent(account.pct_gain)})
              </span>
              <span className={`account-group__stat ${(account.xirr ?? 0) >= 0 ? 'positive' : 'negative'}`}>
                <span className="account-group__stat-label">XIRR</span>
                {formatXirr(account.xirr)}
              </span>
              <span
                className="account-group__view-all"
                role="link"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/transactions?account_id=${account.account_id}`);
                }}
              >
                View transactions →
              </span>
            </button>

            {isOpen && (
              <div className="table-scroll">
                <table className="data-table data-table--nested">
                  <thead>
                    <tr>
                      <th>Scheme</th>
                      <th>Net Units</th>
                      <th>Net Invested</th>
                      <th>Latest NAV</th>
                      <th>Current Value</th>
                      <th>Gain/Loss</th>
                      <th>% Gain</th>
                      <th>XIRR</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {account.schemes.map((s) => (
                      <tr
                        key={s.scheme_code}
                        className="row--clickable"
                        title={`View transactions for ${s.display_name} in ${account.account_name}`}
                        onClick={() =>
                          navigate(
                            `/transactions?account_id=${account.account_id}&scheme_name=${encodeURIComponent(s.scheme_code)}`,
                          )
                        }
                      >
                        <td>{s.display_name}</td>
                        <td>{formatUnits(s.net_units)}</td>
                        <td>{formatCurrency(s.net_invested)}</td>
                        <td>{s.latest_nav === null ? '—' : formatNav(s.latest_nav)}</td>
                        <td>{formatCurrency(s.current_value)}</td>
                        <td className={s.total_gain >= 0 ? 'positive' : 'negative'}>
                          {formatCurrency(s.total_gain)}
                        </td>
                        <td className={(s.pct_gain ?? 0) >= 0 ? 'positive' : 'negative'}>
                          {formatPercent(s.pct_gain)}
                        </td>
                        <td className={(s.xirr ?? 0) >= 0 ? 'positive' : 'negative'}>{formatXirr(s.xirr)}</td>
                        <td>
                          <span
                            className={`status-pill status-pill--${s.status.replace(/\s+/g, '-').toLowerCase()}`}
                          >
                            {s.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
