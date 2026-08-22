"""Commission derivation - shared by manual entry, SIP confirmation, and the
importer so all three can never disagree on the arithmetic.

Every transaction is entered the same way: quantity, NAV, and the final
amount that actually moved at the bank. Commission (stamp duty, transaction
charges, GST, exit load, STT - whatever the broker/RTA deducted) is derived,
never entered directly, and the direction of the derivation flips with the
transaction type:

  PURCHASE / SIP: amount is a debit. You pay charges ON TOP of what reaches
      the fund, so   amount = gross + commission   =>   commission = amount - gross

  REDEMPTION: amount is a credit. Charges are taken OUT of the proceeds
      before the money reaches you, so   amount = gross - commission
      =>   commission = gross - amount

In both directions commission must be >= 0. A negative result always means
a mistyped NAV, quantity, or amount - never a real world state - so it is
rejected rather than stored.
"""

from decimal import Decimal

from models.enums import TransactionType


class InvalidCommissionError(ValueError):
    """Raised when the entered NAV/units/amount imply negative commission."""

    def __init__(self, transaction_type: str, gross: Decimal, amount: Decimal) -> None:
        self.transaction_type = transaction_type
        self.gross = gross
        self.amount = amount
        if transaction_type == TransactionType.PURCHASE:
            hint = (
                f"gross (NAV x units = {gross}) exceeds the amount debited ({amount}). "
                "Check the NAV, units, or amount entered."
            )
        else:
            hint = (
                f"amount credited ({amount}) exceeds gross (NAV x units = {gross}). "
                "Check the NAV, units, or amount entered."
            )
        super().__init__(f"Invalid {transaction_type.lower()}: {hint}")


def compute_commission(
    transaction_type: str,
    nav: Decimal,
    units: Decimal,
    amount: Decimal,
    *,
    tolerance: Decimal = Decimal("0"),
) -> Decimal:
    """Returns the derived commission, >= 0. Raises InvalidCommissionError if
    the inputs imply a negative commission beyond `tolerance`.

    tolerance exists for one reason: historical statement data recorded NAV
    and units already rounded (e.g. to 4dp/3dp), so NAV x units sometimes
    comes out a few paise above the recorded amount even though nothing was
    actually wrong - the true commission is 0 or negligible, not negative.
    Manual entry and SIP confirmation use the default (tolerance=0, strict)
    because there a negative result really does mean a typo; the importer
    passes a small explicit tolerance for exactly this rounding noise. A
    result within tolerance is clamped to 0, not silently kept negative.
    """
    gross = nav * units
    if transaction_type == TransactionType.PURCHASE:
        commission = amount - gross
    elif transaction_type == TransactionType.REDEMPTION:
        commission = gross - amount
    else:
        raise ValueError(f"Unknown transaction type: {transaction_type!r}")

    if commission < 0:
        if abs(commission) <= tolerance:
            return Decimal("0")
        raise InvalidCommissionError(transaction_type, gross, amount)
    return commission


def compute_signed_amount(transaction_type: str, amount: Decimal) -> Decimal:
    """-amount for PURCHASE, +amount for REDEMPTION - mirrors the workbook's
    _CashFlows sheet and feeds XIRR directly.
    """
    if transaction_type == TransactionType.PURCHASE:
        return -amount
    if transaction_type == TransactionType.REDEMPTION:
        return amount
    raise ValueError(f"Unknown transaction type: {transaction_type!r}")
