import { formatCurrency } from '../lib/format';
import type { TransactionType } from '../types/api';

interface CommissionFieldProps {
  type: TransactionType;
  nav: number | null;
  units: number | null;
  amount: number | null;
}

/**
 * Live, read-only commission preview shared by the transaction form and the
 * SIP due-entries table. The formula flips by direction (see
 * backend/app/services/charges.py): on a PURCHASE the amount debited is
 * gross + commission; on a REDEMPTION the amount credited is gross -
 * commission. The server recomputes and validates independently on submit -
 * this is a preview only, so it never blocks entry.
 */
export default function CommissionField({ type, nav, units, amount }: CommissionFieldProps) {
  if (nav === null || units === null || amount === null || nav <= 0 || units <= 0 || amount <= 0) {
    return <span className="commission-field commission-field--empty">—</span>;
  }

  const gross = nav * units;
  const commission = type === 'PURCHASE' ? amount - gross : gross - amount;
  const invalid = commission < -0.005; // a couple of paise of float noise is fine; anything more is a real typo

  if (invalid) {
    const hint =
      type === 'PURCHASE'
        ? `NAV x units (${formatCurrency(gross)}) exceeds the amount entered.`
        : `Amount entered exceeds NAV x units (${formatCurrency(gross)}).`;
    return (
      <span className="commission-field commission-field--invalid" title={hint}>
        Invalid: check NAV/units/amount
      </span>
    );
  }

  return <span className="commission-field">{formatCurrency(Math.max(commission, 0))}</span>;
}
