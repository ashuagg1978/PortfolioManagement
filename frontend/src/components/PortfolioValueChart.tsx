import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { PortfolioHistoryPoint } from '../types/api';
import { formatCurrencyCompact, formatDate, formatPercent } from '../lib/format';

const DAY_MS = 24 * 60 * 60 * 1000;
const POSITIVE = '#15803d';
const NEGATIVE = '#dc2626';
const INVESTED = '#8a97a5';

type Metric = 'pct' | 'value';

interface Range {
  key: string;
  label: string;
  days: number | null; // null = everything
}

// Preset windows, the trading-platform convention: the reader picks a period
// from a fixed row instead of drag-selecting one, which is both faster and
// reproducible (1Y always means the same thing).
const RANGES: Range[] = [
  { key: '1M', label: '1M', days: 30 },
  { key: '3M', label: '3M', days: 91 },
  { key: '6M', label: '6M', days: 182 },
  { key: '1Y', label: '1Y', days: 365 },
  { key: '3Y', label: '3Y', days: 1095 },
  { key: '5Y', label: '5Y', days: 1825 },
  { key: 'ALL', label: 'All', days: null },
];

function parseAsOf(s: string): Date {
  return new Date(s + 'T00:00:00');
}

function daysBetween(a: string, b: string): number {
  return (parseAsOf(b).getTime() - parseAsOf(a).getTime()) / DAY_MS;
}

type Granularity = 'day' | 'month' | 'quarter' | 'year';

// Roughly the width one axis label needs before its neighbour starts to
// overlap it - the tick budget is derived from the measured plot width, so a
// phone gets three labels where a desktop gets nine.
const TICK_LABEL_PX = 88;
const MIN_TICKS = 3;
const MAX_TICKS = 9;
const Y_AXIS_PX = 72;

// How many buckets of a given granularity are still worth labelling at all -
// a legibility limit, independent of how wide the plot happens to be.
const GRANULARITY_LIMIT: Array<[Granularity, number]> = [
  ['day', 63],
  ['month', 18],
  ['quarter', 18],
];

function bucketKey(d: Date, g: Granularity): string {
  switch (g) {
    case 'day':
      return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    case 'month':
      return `${d.getFullYear()}-${d.getMonth()}`;
    case 'quarter':
      return `${d.getFullYear()}-${Math.floor(d.getMonth() / 3)}`;
    case 'year':
      return String(d.getFullYear());
  }
}

// One tick per calendar bucket rather than per fixed pixel gap. Evenly spaced
// ticks land wherever they land, which is how the same month can be labelled
// twice in a row; anchoring to boundaries makes every label distinct and puts
// the gridline where the reader expects it.
function bucketStarts(points: PortfolioHistoryPoint[], g: Granularity): string[] {
  const out: string[] = [];
  let last: string | null = null;
  for (const p of points) {
    const k = bucketKey(parseAsOf(p.as_of), g);
    if (k !== last) {
      out.push(p.as_of);
      last = k;
    }
  }
  return out;
}

function thin(values: string[], max: number): string[] {
  if (values.length <= max) return values;
  const step = Math.ceil(values.length / max);
  return values.filter((_, i) => i % step === 0);
}

// Finest granularity that doesn't crowd the axis; the label format follows the
// granularity (not the raw day count) so two ticks can never render alike.
function pickAxis(
  points: PortfolioHistoryPoint[],
  maxTicks: number,
): { ticks: string[]; granularity: Granularity } {
  for (const [g, limit] of GRANULARITY_LIMIT) {
    const starts = bucketStarts(points, g);
    if (starts.length <= limit) return { ticks: thin(starts, maxTicks), granularity: g };
  }
  return { ticks: thin(bucketStarts(points, 'year'), maxTicks), granularity: 'year' };
}

function formatAxisTick(value: string, granularity: Granularity): string {
  const dt = parseAsOf(value);
  if (granularity === 'year') return dt.toLocaleDateString('en-IN', { year: 'numeric' });
  if (granularity === 'day') return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
  return dt.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
}

// Compact, 0-decimal Y-axis label - formatPercent's 2-decimal precision
// (used in the readout, where there's room) reads too wide for the axis column.
function formatAxisPct(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${Math.round(value)}%`;
}

// The readout re-renders on every crosshair move, so paise are pure noise
// here - unlike the KPI cards, where the exact figure is the point.
const wholeRupees = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

function formatSignedRupees(value: number): string {
  return `${value > 0 ? '+' : ''}${wholeRupees.format(value)}`;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: PortfolioHistoryPoint }>;
  metric?: Metric;
}

// Deliberately terse: the readout above the plot already carries the full
// breakdown for whatever day the crosshair is on, so this only needs to put
// the plotted number next to the pointer - one row per series on the chart.
function ChartTooltip({ active, payload, metric }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div className="portfolio-chart__tooltip">
      <p className="portfolio-chart__tooltip-date">{formatDate(p.as_of)}</p>
      {metric === 'value' ? (
        <>
          <p className="portfolio-chart__tooltip-value">{wholeRupees.format(p.current_value)}</p>
          <p className="portfolio-chart__tooltip-line">
            Invested {wholeRupees.format(p.net_invested)}
          </p>
        </>
      ) : (
        <p
          className="portfolio-chart__tooltip-value"
          style={{ color: (p.pct_gain ?? 0) >= 0 ? POSITIVE : NEGATIVE }}
        >
          {formatPercent(p.pct_gain)}
        </p>
      )}
    </div>
  );
}

export default function PortfolioValueChart({ points }: { points: PortfolioHistoryPoint[] }) {
  const spanDays = useMemo(
    () => (points.length < 2 ? 0 : daysBetween(points[0].as_of, points[points.length - 1].as_of)),
    [points],
  );

  // Only offer windows the data can actually fill, so a six-month-old
  // portfolio doesn't show four buttons that all render the same picture.
  const ranges = useMemo(() => {
    const fits = RANGES.filter((r) => r.days !== null && r.days <= spanDays);
    return [...fits, RANGES[RANGES.length - 1]];
  }, [spanDays]);

  const [rangeKey, setRangeKey] = useState<string>(() =>
    spanDays >= 365 ? '1Y' : 'ALL',
  );
  const [metric, setMetric] = useState<Metric>('pct');
  // Index into `displayed` that the crosshair is currently on; null = not
  // hovering, in which case the readout shows the latest day.
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Measured so the axis can budget its labels; the panel is inside a
  // responsive grid, so a media query on the viewport wouldn't know the
  // plot's actual width.
  const plotRef = useRef<HTMLDivElement>(null);
  const [plotWidth, setPlotWidth] = useState(720);
  useEffect(() => {
    const el = plotRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => {
      const w = entry?.contentRect.width;
      if (w) setPlotWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const range = ranges.find((r) => r.key === rangeKey) ?? RANGES[RANGES.length - 1];

  const displayed = useMemo(() => {
    if (range.days === null || points.length === 0) return points;
    const last = points[points.length - 1].as_of;
    return points.filter((p) => daysBetween(p.as_of, last) <= range.days!);
  }, [points, range]);

  const maxTicks = Math.max(
    MIN_TICKS,
    Math.min(MAX_TICKS, Math.floor((plotWidth - Y_AXIS_PX) / TICK_LABEL_PX)),
  );
  const axis = useMemo(() => pickAxis(displayed, maxTicks), [displayed, maxTicks]);

  const active =
    hoverIndex !== null && hoverIndex >= 0 && hoverIndex < displayed.length
      ? displayed[hoverIndex]
      : displayed[displayed.length - 1];

  // Color the series by the standing at the right edge of the window - the
  // same tone convention KpiCard uses elsewhere.
  const tone = useMemo(() => {
    for (let i = displayed.length - 1; i >= 0; i -= 1) {
      if (displayed[i].pct_gain !== null) return displayed[i].pct_gain! >= 0 ? POSITIVE : NEGATIVE;
    }
    return POSITIVE;
  }, [displayed]);

  // What a range button is really asking ("how did I do over 1Y?"), expressed
  // in percentage points of return. Deliberately not the rupee change in
  // value: fresh SIP contributions inflate that, so it reads as performance
  // while mostly measuring how much was paid in.
  const periodChange = useMemo(() => {
    if (displayed.length < 2) return null;
    const first = displayed[0].pct_gain;
    const last = displayed[displayed.length - 1].pct_gain;
    if (first === null || last === null) return null;
    return last - first;
  }, [displayed]);

  // Recharts' mouse-state type is a large, version-sensitive generic union;
  // read just the one field this component needs, defensively.
  // (recharts 3 types activeTooltipIndex as number | string | null.)
  function handleMouseMove(state: { activeTooltipIndex?: number | string | null }) {
    const i = state?.activeTooltipIndex;
    const n = typeof i === 'string' ? Number(i) : i;
    setHoverIndex(typeof n === 'number' && Number.isFinite(n) ? n : null);
  }

  // Keyboard equivalent of the crosshair, so every value the hover layer
  // exposes is reachable without a pointer.
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const current = hoverIndex ?? displayed.length - 1;
    const next = e.key === 'ArrowLeft' ? current - 1 : current + 1;
    setHoverIndex(Math.max(0, Math.min(displayed.length - 1, next)));
  }

  const gainTone = (active?.pct_gain ?? 0) >= 0 ? POSITIVE : NEGATIVE;

  return (
    <div className="portfolio-chart">
      <div className="portfolio-chart__toolbar">
        <div className="portfolio-chart__ranges" role="group" aria-label="Time range">
          {ranges.map((r) => (
            <button
              key={r.key}
              type="button"
              className={`portfolio-chart__chip${
                r.key === range.key ? ' portfolio-chart__chip--active' : ''
              }`}
              aria-pressed={r.key === range.key}
              onClick={() => {
                setRangeKey(r.key);
                setHoverIndex(null);
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
        <div className="portfolio-chart__ranges" role="group" aria-label="Metric">
          <button
            type="button"
            className={`portfolio-chart__chip${
              metric === 'pct' ? ' portfolio-chart__chip--active' : ''
            }`}
            aria-pressed={metric === 'pct'}
            onClick={() => setMetric('pct')}
          >
            Returns %
          </button>
          <button
            type="button"
            className={`portfolio-chart__chip${
              metric === 'value' ? ' portfolio-chart__chip--active' : ''
            }`}
            aria-pressed={metric === 'value'}
            onClick={() => setMetric('value')}
          >
            Value ₹
          </button>
        </div>
      </div>

      {active && (
        <div className="portfolio-chart__readout">
          <div>
            <p className="portfolio-chart__readout-date">{formatDate(active.as_of)}</p>
            {/* Returns are tone-coloured because the sign is the message; a
                rupee value isn't "good" or "bad", so it stays in ink. */}
            <p
              className="portfolio-chart__readout-hero"
              style={metric === 'pct' ? { color: gainTone } : undefined}
            >
              {metric === 'value'
                ? wholeRupees.format(active.current_value)
                : formatPercent(active.pct_gain)}
            </p>
          </div>
          <dl className="portfolio-chart__stats">
            <div className="portfolio-chart__stat">
              <dt>Value</dt>
              <dd>{wholeRupees.format(active.current_value)}</dd>
            </div>
            <div className="portfolio-chart__stat">
              <dt>Invested</dt>
              <dd>{wholeRupees.format(active.net_invested)}</dd>
            </div>
            <div className="portfolio-chart__stat">
              <dt>P&amp;L</dt>
              <dd style={{ color: gainTone }}>
                {formatSignedRupees(active.current_value - active.net_invested)}
              </dd>
            </div>
            {periodChange !== null && (
              <div className="portfolio-chart__stat">
                <dt>{range.key === 'ALL' ? 'Since start' : `${range.label} change`}</dt>
                <dd style={{ color: periodChange >= 0 ? POSITIVE : NEGATIVE }}>
                  {`${periodChange > 0 ? '+' : ''}${periodChange.toFixed(2)} pts`}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      <div
        ref={plotRef}
        className="portfolio-chart__plot"
        tabIndex={0}
        role="application"
        aria-label={`Portfolio ${metric === 'value' ? 'value' : 'returns'} over ${range.label}. Use left and right arrow keys to read individual days.`}
        onKeyDown={handleKeyDown}
        onBlur={() => setHoverIndex(null)}
      >
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart
            data={displayed}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoverIndex(null)}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <defs>
              <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={tone} stopOpacity={0.28} />
                <stop offset="95%" stopColor={tone} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(17, 32, 49, 0.08)" vertical={false} />
            <XAxis
              dataKey="as_of"
              ticks={axis.ticks}
              interval={0}
              tickFormatter={(v: string) => formatAxisTick(v, axis.granularity)}
              tick={{ fontSize: 12, fill: '#617286' }}
              axisLine={{ stroke: 'rgba(17, 32, 49, 0.12)' }}
              tickLine={false}
            />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(v: number) =>
                metric === 'value' ? formatCurrencyCompact(v) : formatAxisPct(v)
              }
              tick={{ fontSize: 12, fill: '#617286' }}
              axisLine={false}
              tickLine={false}
              width={metric === 'value' ? 72 : 56}
            />
            <Tooltip
              content={<ChartTooltip metric={metric} />}
              cursor={{ stroke: '#8a97a5', strokeWidth: 1, strokeDasharray: '4 4' }}
              wrapperStyle={{ outline: 'none' }}
            />
            <Area
              type="monotone"
              dataKey={metric === 'value' ? 'current_value' : 'pct_gain'}
              stroke={tone}
              strokeWidth={2}
              fill="url(#portfolioFill)"
              isAnimationActive={false}
              connectNulls={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff', fill: tone }}
            />
            {metric === 'value' && (
              <Line
                type="monotone"
                dataKey="net_invested"
                stroke={INVESTED}
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
                isAnimationActive={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff', fill: INVESTED }}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {metric === 'value' && (
        <div className="portfolio-chart__legend">
          <span className="portfolio-chart__legend-item">
            <span className="portfolio-chart__legend-key" style={{ background: tone }} />
            Current value
          </span>
          <span className="portfolio-chart__legend-item">
            <span
              className="portfolio-chart__legend-key portfolio-chart__legend-key--dashed"
              style={{ color: INVESTED }}
            />
            Invested
          </span>
        </div>
      )}
    </div>
  );
}
