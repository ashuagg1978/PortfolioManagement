from models.scheme import Scheme
from services.scheme_names import full_scheme_name


def test_full_scheme_name_combines_name_plan_and_option():
    s = Scheme(scheme_code="998", scheme_name="Kotak Contra Fund", plan="Regular Plan", option="Growth")
    assert full_scheme_name(s) == "Kotak Contra Fund - Regular Plan - Growth"


def test_full_scheme_name_falls_back_gracefully_when_plan_or_option_missing():
    # ~44% of the real AMFI feed has blank Plan/Option (see services/importers/excel_workbook.py) -
    # the combined name must still read sensibly, not trail a stray " - ".
    no_plan_or_option = Scheme(scheme_code="999", scheme_name="SBI FLEXICAP FUND", plan=None, option=None)
    assert full_scheme_name(no_plan_or_option) == "SBI FLEXICAP FUND"

    plan_only = Scheme(scheme_code="997", scheme_name="HDFC Mid Cap Fund", plan="Direct Plan", option=None)
    assert full_scheme_name(plan_only) == "HDFC Mid Cap Fund - Direct Plan"
