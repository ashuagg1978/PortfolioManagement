from datetime import date
from decimal import Decimal

from services.xirr import CashFlow, compute_xirr, scheme_xirr


def test_hand_computed_case():
    # -1000 today, worth 1100 in exactly 1 year -> XIRR = 10%
    flows = [
        CashFlow(date(2023, 1, 1), Decimal("-1000")),
        CashFlow(date(2024, 1, 1), Decimal("1100")),
    ]
    result = compute_xirr(flows)
    assert result is not None
    assert abs(float(result) - 0.10) < 0.001


def test_fewer_than_two_flows_is_none():
    assert compute_xirr([CashFlow(date(2023, 1, 1), Decimal("-1000"))]) is None
    assert compute_xirr([]) is None


def test_no_sign_change_is_none():
    flows = [
        CashFlow(date(2023, 1, 1), Decimal("-1000")),
        CashFlow(date(2023, 6, 1), Decimal("-500")),
    ]
    assert compute_xirr(flows) is None


def test_all_same_date_is_none():
    flows = [
        CashFlow(date(2023, 1, 1), Decimal("-1000")),
        CashFlow(date(2023, 1, 1), Decimal("1050")),
    ]
    assert compute_xirr(flows) is None


def test_fully_redeemed_scheme_still_gets_xirr_without_synthetic_flow():
    # Workbook skips this case entirely (current value <= 0). We don't.
    flows = [
        (date(2023, 1, 1), Decimal("-1000")),
        (date(2024, 1, 1), Decimal("1100")),
    ]
    result = scheme_xirr(flows, current_value=Decimal("0"), as_of=date(2024, 6, 1))
    assert result is not None
    assert abs(float(result) - 0.10) < 0.001


def test_held_scheme_includes_synthetic_current_value_flow():
    flows = [(date(2023, 1, 1), Decimal("-1000"))]
    result = scheme_xirr(flows, current_value=Decimal("1100"), as_of=date(2024, 1, 1))
    assert result is not None
    assert abs(float(result) - 0.10) < 0.001


def test_single_purchase_no_redemption_no_synthetic_flow_is_none():
    # Only one historical flow and current_value is 0 (e.g. data entry
    # error) - not enough to solve.
    result = scheme_xirr([(date(2023, 1, 1), Decimal("-1000"))], Decimal("0"), date(2024, 1, 1))
    assert result is None
