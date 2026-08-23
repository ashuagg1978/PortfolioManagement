from sqlalchemy.orm import Session

from models.portfolio_scheme import PortfolioScheme
from models.scheme import Scheme


def full_scheme_name(scheme: Scheme) -> str:
    """The complete AMFI name including Plan and Option, e.g.
    'Kotak Contra Fund - Regular Plan - Growth' - not just 'Kotak Contra
    Fund'. This is what display_name_for should fall back to whenever a
    scheme has no user-curated portfolio_schemes label yet, since the bare
    scheme_name alone doesn't distinguish Direct from Regular or Growth
    from IDCW (see DATABASE.md#schemes - the same ambiguity that makes
    scheme_code the only safe identifier applies to the name shown on
    screen, not just to lookups).
    """
    parts = [scheme.scheme_name]
    if scheme.plan:
        parts.append(scheme.plan)
    if scheme.option:
        parts.append(scheme.option)
    return " - ".join(parts)


def display_name_for(db: Session, user_id: int, scheme_code: str, fallback: str) -> str:
    """A user's own label for a scheme code, falling back to the AMFI name
    (or the raw code) when they haven't set one.
    """
    ps = (
        db.query(PortfolioScheme)
        .filter(PortfolioScheme.user_id == user_id, PortfolioScheme.scheme_code == scheme_code)
        .first()
    )
    return ps.display_name if ps else fallback
