const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

const compactCurrencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  notation: 'compact',
  maximumFractionDigits: 1,
});

export function formatCurrency(value: number): string {
  return currencyFormatter.format(value);
}

export function formatCurrencyCompact(value: number): string {
  return compactCurrencyFormatter.format(value);
}

export function formatUnits(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

export function formatNav(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export function formatPercent(value: number | null): string {
  if (value === null) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatXirr(value: number | null): string {
  if (value === null) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

export function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value + 'T00:00:00').toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function formatDateTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
