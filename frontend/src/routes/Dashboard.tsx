import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDashboard, syncNav } from '../lib/api';
import { formatCurrency, formatDate, formatPercent, formatXirr } from '../lib/format';
import KpiCard from '../components/KpiCard';
import HoldingsTable from '../components/HoldingsTable';
import AllocationBar, { allocationColor } from '../components/AllocationBar';

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });

  const sync = useMutation({
    mutationFn: syncNav,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
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
        </p>
      )}
      {sync.error && <p className="sync-result sync-result--error">Sync failed: {String(sync.error)}</p>}

      <section className="summary-grid">
        <KpiCard title="Net Invested" value={formatCurrency(data.net_invested)} accent="#1f6feb" />
        <KpiCard title="Current Value" value={formatCurrency(data.current_value)} accent="#1f6feb" />
        <KpiCard
          title="Net Gain / Loss"
          value={formatCurrency(data.net_gain_loss)}
          tone={data.net_gain_loss >= 0 ? 'positive' : 'negative'}
          caption={formatPercent(data.total_return_pct)}
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
    </div>
  );
}
