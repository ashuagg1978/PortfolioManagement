interface KpiCardProps {
  title: string;
  value: string;
  caption?: string;
  accent?: string;
  tone?: 'positive' | 'negative' | 'neutral';
}

export default function KpiCard({ title, value, caption, accent, tone = 'neutral' }: KpiCardProps) {
  return (
    <div className="kpi-card" style={accent ? ({ '--accent': accent } as React.CSSProperties) : undefined}>
      <p className="kpi-card__title">{title}</p>
      <p className={`kpi-card__value kpi-card__value--${tone}`}>{value}</p>
      {caption && <p className="kpi-card__caption">{caption}</p>}
    </div>
  );
}
