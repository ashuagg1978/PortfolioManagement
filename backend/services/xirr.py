"""XIRR via pyxirr - the same algorithm Excel's XIRR() uses, so results are
directly comparable to the workbook this app replaces.

Cash-flow sign convention: negative = money out (purchase), positive = money
in (redemption, or the synthetic "what it's worth if I sold today" flow).
This matches Transaction.signed_amount exactly, so a scheme's flows are just
its signed_amount column plus one synthetic flow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pyxirr


@dataclass(frozen=True, slots=True)
class CashFlow:
    date: date
    amount: Decimal


def compute_xirr(flows: list[CashFlow]) -> Decimal | None:
    """Returns None (UI renders "-") for every degenerate case rather than
    letting an exception or an infinite/NaN result reach the API:
    fewer than 2 flows, all dates identical, no sign change, or solver
    non-convergence.
    """
    if len(flows) < 2:
        return None
    dates = [f.date for f in flows]
    amounts = [float(f.amount) for f in flows]

    try:
        result = pyxirr.xirr(dates, amounts)
    except Exception:
        # Covers pyxirr.InvalidPaymentsError (no sign change / too few
        # flows) and any other solver failure.
        return None

    if result is None or not math.isfinite(result):
        # All-same-date flows solve to +/-inf rather than raising.
        return None

    return Decimal(str(round(result, 6)))


def scheme_xirr(
    signed_flows: list[tuple[date, Decimal]], current_value: Decimal, as_of: date
) -> Decimal | None:
    """XIRR for one scheme: its transaction flows plus a synthetic
    "sell everything today" flow - omitted when current value is 0 so a
    fully-redeemed scheme's real historical XIRR isn't diluted by a
    meaningless zero flow (the workbook skips XIRR entirely in this case,
    losing the figure; this only omits the synthetic flow).
    """
    flows = [CashFlow(date=d, amount=amt) for d, amt in signed_flows]
    if current_value > 0:
        flows.append(CashFlow(date=as_of, amount=current_value))
    return compute_xirr(flows)
