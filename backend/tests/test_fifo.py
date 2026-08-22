from datetime import date
from decimal import Decimal

import pytest

from models.enums import TransactionType
from services.fifo import LedgerEntry, OverRedemptionError, run_fifo


def entry(id_, d, type_, units, amount):
    return LedgerEntry(id=id_, date=d, type=type_, units=Decimal(units), amount=Decimal(amount))


def test_single_purchase_no_redemption():
    entries = [entry(1, date(2024, 1, 1), TransactionType.PURCHASE, "100", "10000")]
    result = run_fifo(entries)
    assert result.units_held == Decimal("100")
    assert result.avg_cost_nav == Decimal("100")
    assert result.realized_gain == 0


def test_partial_redemption_consumes_oldest_lot_first():
    entries = [
        entry(1, date(2024, 1, 1), TransactionType.PURCHASE, "100", "10000"),  # cost/unit 100
        entry(2, date(2024, 6, 1), TransactionType.PURCHASE, "100", "12000"),  # cost/unit 120
        entry(3, date(2024, 7, 1), TransactionType.REDEMPTION, "50", "6000"),  # proceeds/unit 120
    ]
    result = run_fifo(entries)
    # 50 units sold FIFO come entirely from lot 1 (cost/unit 100)
    assert len(result.consumptions) == 1
    c = result.consumptions[0]
    assert c.lot_transaction_id == 1
    assert c.units == Decimal("50")
    assert c.cost == Decimal("5000")  # 50 * 100
    assert c.proceeds == Decimal("6000")
    assert c.gain == Decimal("1000")
    # remaining holdings: 50 units left in lot 1, all 100 units in lot 2
    assert result.units_held == Decimal("150")


def test_redemption_spanning_multiple_lots():
    entries = [
        entry(1, date(2024, 1, 1), TransactionType.PURCHASE, "50", "5000"),  # cost/unit 100
        entry(2, date(2024, 2, 1), TransactionType.PURCHASE, "50", "6000"),  # cost/unit 120
        entry(3, date(2024, 7, 1), TransactionType.REDEMPTION, "80", "9600"),  # proceeds/unit 120
    ]
    result = run_fifo(entries)
    assert len(result.consumptions) == 2
    first, second = result.consumptions
    assert first.lot_transaction_id == 1 and first.units == Decimal("50")
    assert second.lot_transaction_id == 2 and second.units == Decimal("30")
    assert result.units_held == Decimal("20")  # 20 left in lot 2


def test_full_redemption_empties_holding():
    entries = [
        entry(1, date(2024, 1, 1), TransactionType.PURCHASE, "100", "10000"),
        entry(2, date(2024, 7, 1), TransactionType.REDEMPTION, "100", "11000"),
    ]
    result = run_fifo(entries)
    assert result.units_held == 0
    assert result.avg_cost_nav is None
    assert result.realized_gain == Decimal("1000")


def test_over_redemption_raises():
    entries = [
        entry(1, date(2024, 1, 1), TransactionType.PURCHASE, "50", "5000"),
        entry(2, date(2024, 7, 1), TransactionType.REDEMPTION, "100", "11000"),
    ]
    with pytest.raises(OverRedemptionError):
        run_fifo(entries)


def test_ltcg_vs_stcg_split():
    entries = [
        entry(1, date(2023, 1, 1), TransactionType.PURCHASE, "50", "5000"),  # held > 365 days
        entry(2, date(2024, 6, 1), TransactionType.PURCHASE, "50", "6000"),  # held < 365 days
        entry(3, date(2024, 7, 1), TransactionType.REDEMPTION, "100", "13000"),
    ]
    result = run_fifo(entries)
    terms = {c.lot_transaction_id: c.term for c in result.consumptions}
    assert terms[1] == "LTCG"
    assert terms[2] == "STCG"


def test_soft_delete_reflected_by_excluding_from_input():
    # The service layer excludes is_deleted rows before calling run_fifo, so
    # simulating a soft-deleted purchase is just: don't include it.
    with_deleted = [
        entry(1, date(2024, 1, 1), TransactionType.PURCHASE, "100", "10000"),
        entry(2, date(2024, 2, 1), TransactionType.PURCHASE, "50", "6000"),
    ]
    without_deleted_txn_1 = with_deleted[1:]
    result = run_fifo(without_deleted_txn_1)
    assert result.units_held == Decimal("50")
    assert result.avg_cost_nav == Decimal("120")
