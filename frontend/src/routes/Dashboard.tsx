import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDashboard, getPortfolioHistory, syncNav } from '../lib/api';
import { formatCurrency, formatDate, formatPercent, formatXirr } from '../lib/format';
import KpiCard from '../components/KpiCard';
import HoldingsTable from '../components/HoldingsTable';
import AllocationBar, { allocationColor } from '../components/AllocationBar';
import AccountBreakdown from '../components/AccountBreakdown';
import PortfolioValueChart from '../components/PortfolioValueChart';

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });
  const history = useQuery({ queryKey: ['portfolio-history'], queryFn: getPortfolioHistory });

  const sync = useMutation({
    mutationFn: syncNav,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio-history'] });
    },
  });

  if (isLoading) return <p className="empty-state">Loading…</p>;
  if (error || !data) return <p className="empty-state">Could not load the dashboard.</p>;

  const allocation = [...data.holdings]
    .filter((h) => h.current_value > 0)
    .sort((a, b) => b.current_value - a.current_value)
    .map((h, i) => ({
      label: h.display_name,
      pct: data.current_value > 0 ? (h.current_value / data.current_value) * 100 : 0,
      color: allocationColor(i),
    }));

  return (
    <div className="page">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">
            {data.nav_as_of ? `As of ${formatDate(data.nav_as_of)}` : 'NAV not yet synced'}
          </p>
          <h2>Portfolio overview</h2>
        </div>
        <button className="btn btn--primary" onClick={() => sync.mutate()} disabled={sync.isPending}>
          {sync.isPending ? 'Syncing…' : 'Sync NAV'}
        </button>
      </section>

      {sync.data && (
        <p className="sync-result">
          Synced {sync.data.rows_upserted.toLocaleString('en-IN')} schemes
          {sync.data.rows_skipped > 0 && ` (${sync.data.rows_skipped} skipped)`} in {sync.data.duration_ms}ms.
          {sync.data.history_schemes_synced > 0 && (
            <>
              {' '}
              Value history updated for {sync.data.history_schemes_synced} holding
              {sync.data.history_schemes_synced === 1 ? '' : 's'}
              {sync.data.history_schemes_failed > 0 &&
                ` (${sync.data.history_schemes_failed} unavailable)`}
              .
            </>
          )}
        </p>
      )}
      {sync.error && <p className="sync-result sync-result--error">Sync failed: {String(sync.error)}</p>}

      <section className="summary-grid">
        <KpiCard title="Net Invested" value={formatCurrency(data.net_invested)} accent="#1f6feb" />
        <KpiCard
          title="Net Gain/Loss %"
          value={formatPercent(data.total_return_pct)}
          tone={data.net_gain_loss >= 0 ? 'positive' : 'negative'}
          accent={data.net_gain_loss >= 0 ? '#15803d' : '#dc2626'}
        />
        <KpiCard
          title="Net Gain / Loss"
          value={formatCurrency(data.net_gain_loss)}
          tone={data.net_gain_loss >= 0 ? 'positive' : 'negative'}
          accent={data.net_gain_loss >= 0 ? '#15803d' : '#dc2626'}
        />
        <KpiCard title="Active Schemes" value={String(data.active_schemes)} accent="#a855f7" />
        <KpiCard
          title="Portfolio XIRR"
          value={formatXirr(data.portfolio_xirr)}
          tone={(data.portfolio_xirr ?? 0) >= 0 ? 'positive' : 'negative'}
          accent="#f59e0b"
        />
        <KpiCard
          title="Commission Paid"
          value={formatCurrency(data.total_commission_paid)}
          caption="Across all confirmed transactions"
          accent="#65a30d"
        />
      </section>

      <section className="content-grid content-grid--single">
        <article className="panel panel--wide">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Performance over time</p>
              <h3>Portfolio performance</h3>
            </div>
          </div>
          {history.isLoading ? (
            <p className="empty-state">Loading…</p>
          ) : !history.data || history.data.length === 0 ? (
            <p className="empty-state">
              No performance history yet — click Sync NAV to fetch historical NAVs for your holdings.
            </p>
          ) : (
            <PortfolioValueChart points={history.data} />
          )}
        </article>
      </section>

      <section className="content-grid">
        <article className="panel">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Allocation</p>
              <h3>Asset mix</h3>
            </div>
          </div>
          <div className="allocation-list">
            {allocation.length === 0 ? (
              <p className="empty-state">No current holdings.</p>
            ) : (
              allocation.map((a) => <AllocationBar key={a.label} {...a} />)
            )}
          </div>
        </article>

        <article className="panel panel--wide">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">Holdings</p>
              <h3>MF-wise breakdown</h3>
            </div>
          </div>
          <HoldingsTable holdings={data.holdings} />
        </article>
      </section>

      <section className="content-grid content-grid--single">
        <article className="panel panel--wide">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">By account, then scheme</p>
              <h3>Account-wise breakdown</h3>
            </div>
          </div>
          <AccountBreakdown accounts={data.by_account} />
        </article>
      </section>
    </div>
  );
}
