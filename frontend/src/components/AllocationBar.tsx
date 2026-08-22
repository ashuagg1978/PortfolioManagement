interface AllocationBarProps {
  label: string;
  pct: number;
  color: string;
}

export default function AllocationBar({ label, pct, color }: AllocationBarProps) {
  return (
    <div className="allocation-row">
      <div className="allocation-row__label">
        <span className="allocation-row__dot" style={{ background: color }} />
        {label}
      </div>
      <div className="allocation-row__track">
        <div className="allocation-row__fill" style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
      </div>
      <div className="allocation-row__pct">{pct.toFixed(1)}%</div>
    </div>
  );
}

export function allocationColor(index: number): string {
  const palette = ['#1f6feb', '#f59e0b', '#15803d', '#a855f7', '#ec4899', '#0891b2', '#dc2626', '#65a30d'];
  return palette[index % palette.length];
}
