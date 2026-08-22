from decimal import Decimal

import pytest

from models.enums import TransactionType
from services.charges import InvalidCommissionError, compute_commission, compute_signed_amount


def test_purchase_commission_is_amount_minus_gross():
    # Rs 5000 SIP, NAV 145.5090 -> 34.243 units bought.
    nav = Decimal("145.5090")
    units = Decimal("34.243")
    amount = Decimal("5000.00")
    commission = compute_commission(TransactionType.PURCHASE, nav, units, amount)
    gross = nav * units
    assert commission == amount - gross
    assert commission >= 0


def test_redemption_commission_is_gross_minus_amount():
    nav = Decimal("150.0000")
    units = Decimal("100.000000")
    amount = Decimal("14950.00")  # gross 15000, exit load/STT ate 50
    commission = compute_commission(TransactionType.REDEMPTION, nav, units, amount)
    assert commission == Decimal("50.00")


def test_purchase_negative_commission_rejected():
    # amount less than gross implies negative commission - mistyped input.
    with pytest.raises(InvalidCommissionError):
        compute_commission(
            TransactionType.PURCHASE, Decimal("100"), Decimal("50"), Decimal("4999")
        )


def test_redemption_negative_commission_rejected():
    # amount received more than gross implies negative commission.
    with pytest.raises(InvalidCommissionError):
        compute_commission(
            TransactionType.REDEMPTION, Decimal("100"), Decimal("50"), Decimal("5001")
        )


def test_zero_commission_is_valid():
    commission = compute_commission(
        TransactionType.PURCHASE, Decimal("100"), Decimal("50"), Decimal("5000")
    )
    assert commission == 0


def test_signed_amount_purchase_is_negative():
    assert compute_signed_amount(TransactionType.PURCHASE, Decimal("100")) == Decimal("-100")


def test_signed_amount_redemption_is_positive():
    assert compute_signed_amount(TransactionType.REDEMPTION, Decimal("100")) == Decimal("100")
