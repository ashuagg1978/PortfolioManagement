"""Pure unit tests for the day-wise portfolio-value sweep - no DB, same
style as test_fifo.py/test_xirr.py: plain dict/Decimal inputs built directly.
"""

from datetime import date, timedelta
from decimal import Decimal

from models.enums import TransactionType
from services.portfolio_history import TxnEvent, _sweep


def d(offset_days):
    """Day `offset_days` after an arbitrary fixed anchor, so tests don't
    hardcode a real calendar and read as relative day numbers."""
    return date(2024, 1, 1) + timedelta(days=offset_days)


def buy(day, id_, units, amount):
    return TxnEvent(txn_date=day, id=id_, type=TransactionType.PURCHASE, units=Decimal(units), amount=Decimal(amount))


def sell(day, id_, units, amount):
    return TxnEvent(txn_date=day, id=id_, type=TransactionType.REDEMPTION, units=Decimal(units), amount=Decimal(amount))


def by_date(series):
    return {p.as_of: p for p in series}


def test_single_scheme_single_purchase_flat_value_and_pct():
    txn_events = {"S1": [buy(d(0), 1, "100", "1000")]}  # cost/unit 10
    nav_events = {"S1": [(d(0), Decimal("10"))]}
    series = _sweep(txn_events, nav_events, d(0), d(3))
    for p in series:
        assert p.current_value == Decimal("1000")
        assert p.net_invested == Decimal("1000")
        assert p.pct_gain == Decimal("0")  # bought at cost, NAV unchanged - flat


def test_pct_gain_reflects_nav_appreciation():
    txn_events = {"S1": [buy(d(0), 1, "100", "1000")]}  # cost/unit 10
    nav_events = {"S1": [(d(0), Decimal("10")), (d(1), Decimal("11"))]}
    series = by_date(_sweep(txn_events, nav_events, d(0), d(1)))
    assert series[d(0)].pct_gain == Decimal("0")
    # NAV rose 10 -> 11 (+10%); value 1000 -> 1100, invested still 1000
    assert series[d(1)].current_value == Decimal("1100")
    assert series[d(1)].net_invested == Decimal("1000")
    assert series[d(1)].pct_gain == Decimal("10")


def test_weekend_forward_fills_last_nav():
    txn_events = {"S1": [buy(d(0), 1, "10", "1000")]}  # cost/unit 100
    nav_events = {"S1": [(d(0), Decimal("100")), (d(3), Decimal("110"))]}
    series = by_date(_sweep(txn_events, nav_events, d(0), d(3)))
    assert series[d(0)].current_value == Decimal("1000")
    assert series[d(1)].current_value == Decimal("1000")  # Saturday - carries Friday's NAV
    assert series[d(2)].current_value == Decimal("1000")  # Sunday - same
    assert series[d(3)].current_value == Decimal("1100")  # Monday - new NAV lands


def test_scheme_with_no_nav_yet_contributes_zero_value_but_invested_still_counts():
    txn_events = {"S1": [buy(d(0), 1, "10", "1000")]}
    nav_events = {"S1": [(d(5), Decimal("100"))]}  # NAV history starts 5 days later
    series = by_date(_sweep(txn_events, nav_events, d(0), d(6)))
    for i in range(5):
        p = series[d(i)]
        assert p.current_value == Decimal("0")
        assert p.net_invested == Decimal("1000")  # money was invested, just no NAV to value it yet
        assert p.pct_gain == Decimal("-100")  # (0 - 1000) / 1000 * 100
    assert series[d(5)].current_value == Decimal("1000")
    assert series[d(5)].pct_gain == Decimal("0")


def test_redemption_reduces_net_invested_via_fifo_not_plain_cash_netting():
    # Two lots at different costs; redemption consumes the OLDER (cheaper)
    # lot first - net_invested after must reflect the remaining lot's cost,
    # not (total purchased - redemption amount).
    txn_events = {
        "S1": [
            buy(d(0), 1, "100", "1000"),  # cost/unit 10
            buy(d(1), 2, "100", "1500"),  # cost/unit 15
            sell(d(2), 3, "100", "1300"),  # sells the 100 units from lot 1 (cost 1000)
        ]
    }
    nav_events = {"S1": [(d(0), Decimal("10")), (d(2), Decimal("13"))]}
    series = by_date(_sweep(txn_events, nav_events, d(0), d(2)))
    p = series[d(2)]
    assert p.net_invested == Decimal("1500")  # only lot 2's cost remains, not 2500-1300=1200
    assert p.current_value == Decimal("1300")  # 100 units left * NAV 13


def test_fully_redeemed_scheme_drops_net_invested_and_value_to_zero():
    txn_events = {
        "S1": [
            buy(d(0), 1, "10", "1000"),
            sell(d(2), 2, "10", "1200"),
        ]
    }
    nav_events = {"S1": [(d(0), Decimal("100"))]}
    series = by_date(_sweep(txn_events, nav_events, d(0), d(3)))
    assert series[d(1)].current_value == Decimal("1000")
    assert series[d(2)].current_value == Decimal("0")
    assert series[d(2)].net_invested == Decimal("0")
    assert series[d(2)].pct_gain is None  # nothing left invested - undefined, not a fake 0%
    assert series[d(3)].pct_gain is None


def test_multi_scheme_sums_correctly():
    txn_events = {
        "S1": [buy(d(0), 1, "10", "1000")],
        "S2": [buy(d(1), 2, "5", "1000")],
    }
    nav_events = {
        "S1": [(d(0), Decimal("100"))],
        "S2": [(d(1), Decimal("200"))],
    }
    series = by_date(_sweep(txn_events, nav_events, d(0), d(2)))
    assert series[d(0)].current_value == Decimal("1000")  # only S1 exists yet
    assert series[d(0)].net_invested == Decimal("1000")
    assert series[d(1)].current_value == Decimal("2000")  # S1 (1000) + S2 (5*200=1000)
    assert series[d(1)].net_invested == Decimal("2000")
    assert series[d(2)].current_value == Decimal("2000")


def test_series_starts_on_first_transaction_date_and_reflects_day_one_purchase():
    txn_events = {"S1": [buy(d(0), 1, "10", "500")]}
    nav_events = {"S1": [(d(0), Decimal("50"))]}
    series = _sweep(txn_events, nav_events, d(0), d(0))
    assert len(series) == 1
    assert series[0].as_of == d(0)
    assert series[0].current_value == Decimal("500")  # day 1 already reflects the purchase


def test_today_carries_forward_last_known_nav_when_unsynced():
    txn_events = {"S1": [buy(d(0), 1, "10", "1000")]}
    nav_events = {"S1": [(d(0), Decimal("100"))]}
    series = _sweep(txn_events, nav_events, d(0), d(10))
    assert series[-1].as_of == d(10)
    assert series[-1].current_value == Decimal("1000")


def test_same_day_purchase_and_redemption_apply_in_stable_id_order():
    # Both dated d(0): a purchase (id 1) then a same-day redemption (id 2) -
    # the sort key (date, id) must apply the purchase first so the
    # redemption has a lot to consume, not raise/skip.
    txn_events = {
        "S1": [
            sell(d(0), 2, "5", "60"),  # appended out of id order on purpose
            buy(d(0), 1, "10", "100"),
        ]
    }
    nav_events = {"S1": [(d(0), Decimal("10"))]}
    # _sweep expects pre-sorted input in real use (compute_portfolio_value_history
    # sorts by (txn_date, id) before calling) - sort here the same way.
    txn_events["S1"].sort(key=lambda e: (e.txn_date, e.id))
    series = _sweep(txn_events, nav_events, d(0), d(0))
    p = series[0]
    assert p.net_invested == Decimal("50")  # 10 units bought (cost 100) - 5 redeemed (cost 50)
    assert p.current_value == Decimal("50")  # 5 units left * NAV 10
