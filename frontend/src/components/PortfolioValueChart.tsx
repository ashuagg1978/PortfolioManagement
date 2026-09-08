import { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { PortfolioHistoryPoint } from '../types/api';
import { formatCurrency, formatDate, formatPercent } from '../lib/format';

const DAY_MS = 24 * 60 * 60 * 1000;
const POSITIVE = '#15803d';
const NEGATIVE = '#dc2626';

function parseAsOf(s: string): Date {
  return new Date(s + 'T00:00:00');
}

// Trading-chart-style adaptive axis labels: the same daily series is always
// plotted (no real resampling - see the plan's "smooth zoom" decision), but
// the tick format switches granularity based on how much time is currently
// visible, so zooming out reads as day -> week/month -> quarter -> year.
function formatAxisTick(value: string, visibleDays: number): string {
  const dt = parseAsOf(value);
  if (visibleDays > 730) return dt.toLocaleDateString('en-IN', { year: 'numeric' });
  if (visibleDays > 180) return dt.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
  if (visibleDays > 30) return dt.toLocaleDateString('en-IN', { month: 'short' });
  return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

// Compact, 0-decimal Y-axis label - formatPercent's 2-decimal-place
// precision (used in the tooltip, where there's room) reads too wide for a
// 56px axis column.
function formatAxisPct(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${Math.round(value)}%`;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: PortfolioHistoryPoint }>;
}

function ChartTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  const tone = (p.pct_gain ?? 0) >= 0 ? POSITIVE : NEGATIVE;
  return (
    <div className="portfolio-chart__tooltip">
      <p className="portfolio-chart__tooltip-date">{formatDate(p.as_of)}</p>
      <p className="portfolio-chart__tooltip-pct" style={{ color: tone }}>
        {formatPercent(p.pct_gain)}
      </p>
      <p className="portfolio-chart__tooltip-line">Value: {formatCurrency(p.current_value)}</p>
      <p className="portfolio-chart__tooltip-line">Invested: {formatCurrency(p.net_invested)}</p>
    </div>
  );
}

export default function PortfolioValueChart({ points }: { points: PortfolioHistoryPoint[] }) {
  // Zoom domain, tracked as `as_of` bounds (not array indices) so it stays
  // correct regardless of how the underlying series is sliced. null/null =
  // full range.
  const [left, setLeft] = useState<string | null>(null);
  const [right, setRight] = useState<string | null>(null);
  // In-progress drag selection, shown as a ReferenceArea overlay.
  const [refLeft, setRefLeft] = useState<string | null>(null);
  const [refRight, setRefRight] = useState<string | null>(null);

  const indexByDate = useMemo(() => {
    const m = new Map<string, number>();
    points.forEach((p, i) => m.set(p.as_of, i));
    return m;
  }, [points]);

  const isZoomed = left !== null && right !== null;

  const displayed = useMemo(() => {
    if (!isZoomed) return points;
    const li = indexByDate.get(left!) ?? 0;
    const ri = indexByDate.get(right!) ?? points.length - 1;
    const [lo, hi] = li <= ri ? [li, ri] : [ri, li];
    return points.slice(lo, hi + 1);
  }, [points, left, right, isZoomed, indexByDate]);

  const visibleDays = useMemo(() => {
    if (displayed.length < 2) return 0;
    const start = parseAsOf(displayed[0].as_of).getTime();
    const end = parseAsOf(displayed[displayed.length - 1].as_of).getTime();
    return (end - start) / DAY_MS;
  }, [displayed]);

  // Color the whole series by its current (rightmost) standing, same tone
  // convention KpiCard uses elsewhere - a single line can't honestly split
  // color at every zero-crossing without much more machinery, and "where do
  // I stand right now" is the more useful read at a glance.
  const tone = useMemo(() => {
    for (let i = displayed.length - 1; i >= 0; i -= 1) {
      if (displayed[i].pct_gain !== null) return displayed[i].pct_gain! >= 0 ? POSITIVE : NEGATIVE;
    }
    return POSITIVE;
  }, [displayed]);

  // Recharts' own mouse-event state type is a large, version-sensitive
  // generic union that isn't worth fighting here - just read the one field
  // this component needs, defensively.
  function handleMouseDown(state: { activeLabel?: string | number }) {
    if (state?.activeLabel !== undefined) setRefLeft(String(state.activeLabel));
  }
  function handleMouseMove(state: { activeLabel?: string | number }) {
    if (refLeft && state?.activeLabel !== undefined) setRefRight(String(state.activeLabel));
  }
  function handleMouseUp() {
    if (refLeft && refRight && refLeft !== refRight) {
      setLeft(refLeft);
      setRight(refRight);
    }
    setRefLeft(null);
    setRefRight(null);
  }
  function resetZoom() {
    setLeft(null);
    setRight(null);
  }

  return (
    <div className="portfolio-chart">
      {isZoomed && (
        <button type="button" className="btn btn--small portfolio-chart__reset" onClick={resetZoom}>
          Reset zoom
        </button>
      )}
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart
          data={displayed}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="portfolioPctFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={tone} stopOpacity={0.28} />
              <stop offset="95%" stopColor={tone} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(17, 32, 49, 0.08)" vertical={false} />
          <XAxis
            dataKey="as_of"
            tickFormatter={(v: string) => formatAxisTick(v, visibleDays)}
            tick={{ fontSize: 12, fill: '#617286' }}
            axisLine={{ stroke: 'rgba(17, 32, 49, 0.12)' }}
            tickLine={false}
            minTickGap={48}
          />
          <YAxis
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => formatAxisPct(v)}
            tick={{ fontSize: 12, fill: '#617286' }}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            content={<ChartTooltip />}
            wrapperStyle={{ outline: 'none' }}
          />
          <Area
            type="monotone"
            dataKey="pct_gain"
            stroke={tone}
            strokeWidth={2}
            fill="url(#portfolioPctFill)"
            isAnimationActive={false}
            connectNulls={false}
          />
          {refLeft && refRight && (
            <ReferenceArea x1={refLeft} x2={refRight} strokeOpacity={0.3} fill="#1f6feb" fillOpacity={0.12} />
          )}
        </AreaChart>
      </ResponsiveContainer>
      <p className="portfolio-chart__hint">Drag across the chart to zoom into a date range.</p>
    </div>
  );
}
